"""Worker recovery and API shape checks against the adapter contract."""
import json
from types import SimpleNamespace

from backend.app.adapters.contracts import Job
from backend.tests.test_platform import platform, study_setup, RecordingAdapter


def test_paused_video_resumes_from_fresh_server_play_time(platform):
    class Video(RecordingAdapter):
        writes = 0
        confirms = True
        chapter_confirmed = True
        recorded_positions = []

        def list_jobs(self, course, chapter):
            return [Job("video-1", "300", "video", "Video", type(self).writes > 0,
                        0, {"playTime": 42000}, {})]

        def execute(self, course, job, control, progress):
            self.recorded_positions.append(job.metadata["playTime"])
            super().execute(course, job, control, progress)

    worker, task = study_setup(platform, Video)
    checkpoint = {"runtime": "original-console", "pending": {"300:video-1": {"kind": "video", "sent_at": 1}}}
    worker.checkpoint(task["id"], checkpoint)
    worker.service.action(task["id"], "pause")
    worker.run_task(task)
    assert worker.db.one("SELECT state FROM tasks")["state"] == "paused"
    worker.service.action(task["id"], "resume")
    worker.run_task(worker.claim())
    assert Video.writes == 1
    assert Video.recorded_positions == [42000]
    assert worker.db.one("SELECT state FROM tasks")["state"] == "succeeded"
    assert not json.loads(worker.db.one("SELECT checkpoint FROM tasks")["checkpoint"])["pending"]


def test_video_without_server_playtime_waits_for_confirmation(platform):
    class Video(RecordingAdapter):
        writes = 0

        def list_jobs(self, course, chapter):
            return [Job("video-1", "300", "video", "Video", False, 0, {}, {})]

    worker, task = study_setup(platform, Video)
    checkpoint = {"runtime": "original-console", "pending": {"300:video-1": {"kind": "video"}}}
    worker.checkpoint(task["id"], checkpoint)
    task["checkpoint"] = json.dumps(checkpoint)
    worker.run_task(task)
    assert Video.writes == 0
    assert worker.db.one("SELECT state FROM tasks")["state"] == "awaiting_confirmation"


def test_server_confirmed_chapter_skips_card_fetch_and_clears_pending(platform):
    class Completed(RecordingAdapter):
        writes = 0

        def list_chapters(self, course):
            return [{"id": "300", "title": "Chapter", "jobCount": 1,
                     "has_finished": True, "need_unlock": False}]

        def list_jobs(self, course, chapter):
            raise AssertionError("completed chapter requested cards")

    worker, task = study_setup(platform, Completed)
    checkpoint = {"runtime": "original-console", "pending": {"300:video-1": {"kind": "video"}}}
    worker.checkpoint(task["id"], checkpoint)
    task["checkpoint"] = json.dumps(checkpoint)
    worker.run_task(task)
    row = worker.db.one("SELECT * FROM tasks")
    assert row["state"] == "succeeded"
    assert row["server_state"] == "confirmed"
    assert not json.loads(row["checkpoint"])["pending"]
    assert Completed.writes == 0

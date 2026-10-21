"""Durable assessment execution and server reconciliation."""
import time

from .answering import resolve_answer


class AssessmentWorker:
    def remember_questions(self, task, chapter_id, job_id, questions):
        self.db.execute("""INSERT INTO question_sets(course_id,chapter_id,job_id,payload,updated_at)
            VALUES(?,?,?,?,?) ON CONFLICT(course_id,chapter_id,job_id) DO UPDATE SET
            payload=excluded.payload,updated_at=excluded.updated_at""",
            (task["course_id"], chapter_id, job_id, self.vault.seal(questions), time.time()))

    def answer_paper(self, task, course, paper, adapter, checkpoint, key):
        options = checkpoint["options"]
        answers = {}
        for index, question in enumerate(paper["questions"]):
            self.control(task["id"])
            answer = resolve_answer(self.service, adapter, course, question, options["answer_mode"])
            if answer:
                answers[question["id"]] = answer
            self.db.log(f"答题进度 {index + 1}/{len(paper['questions'])}，已匹配 {len(answers)} 题", task["id"])
        if not answers:
            return {"saved": False, "submitted": False, "complete": False}
        previous = checkpoint["pending"].get(key)
        checkpoint["pending"][key] = {"kind": "assessment", "phase": "writing", "at": time.time()}
        self.checkpoint(task["id"], checkpoint)

        def restore_unsent():
            if previous is None:
                checkpoint["pending"].pop(key, None)
            else:
                checkpoint["pending"][key] = previous
            self.checkpoint(task["id"], checkpoint)

        try:
            self.control(task["id"])
        except BaseException:
            restore_unsent()
            raise
        try:
            result = adapter.save_answers(paper["id"], answers, options["submit_mode"] != "save", options["submit_mode"] == "complete")
        except BaseException as error:
            if getattr(error, "rpc_request_sent", None) is False:
                restore_unsent()
            raise
        checkpoint.setdefault("papers", {})[key] = result
        checkpoint["pending"].pop(key, None)
        self.checkpoint(task["id"], checkpoint)
        self.db.log("答案已提交，等待服务端状态回读" if result["submitted"] else "答案已保存，试卷保留待交卷状态", task["id"])
        return result

    def study_assessments(self, task, course, adapter, checkpoint):
        options = checkpoint["options"]
        kinds = tuple(k for k in ("work", "exam") if options[k])
        if not kinds:
            return False, False
        items = adapter.list_assessments(course, options["work"], options["exam"])
        self.service.save_assessments(task["course_id"], items, kinds)
        if options["answer_mode"] == "off":
            return False, False
        manual, unconfirmed = False, False
        for item in items:
            self.control(task["id"])
            key = item["kind"] + ":" + item["id"]
            if item["status"] in ("已完成", "已提交", "已交卷", "待批阅", "已批阅"):
                checkpoint["pending"].pop(key, None)
                self.checkpoint(task["id"], checkpoint)
                continue
            if key in checkpoint["pending"]:
                unconfirmed = True
                continue
            if key in checkpoint.get("papers", {}):
                manual = True
                continue
            ready = item.get("ready", item["status"] in ("待做", "未完成", "未提交", "待考试", "进行中", "未交", "待重做", "待重考"))
            if not ready:
                manual = True
                continue
            # Opening an exam can start its timer. Reconcile before reopening after a crash.
            checkpoint["pending"][key] = {"kind": "assessment", "phase": "opening", "at": time.time()}
            self.checkpoint(task["id"], checkpoint)
            paper = adapter.assessment_questions(course, item)
            self.remember_questions(task, item["kind"], item["id"], paper["questions"])
            result = self.answer_paper(task, course, paper, adapter, checkpoint, key)
            if not result["saved"]:
                checkpoint["pending"].pop(key, None)
                checkpoint.setdefault("papers", {})[key] = result
                self.checkpoint(task["id"], checkpoint)
                manual = True
            elif not result["submitted"]:
                manual = True
        fresh = adapter.list_assessments(course, options["work"], options["exam"])
        self.service.save_assessments(task["course_id"], fresh, kinds)
        by_key = {(item["kind"], item["id"]): item for item in fresh}
        for previous in items:
            current = by_key.get((previous["kind"], previous["id"]))
            if current is None:
                unconfirmed = True
        for item in fresh:
            if item["status"] not in ("已完成", "已提交", "已交卷", "待批阅", "已批阅"):
                unconfirmed = True
        return manual, unconfirmed

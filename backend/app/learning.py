"""Learning rules shared by task creation, execution and the Web console."""
DEFAULT_RULES = {
    "video_mode": "normal", "media_client": "desktop", "audio": True,
    "document": True, "read": True, "hyperlink": True, "chapter_test": True,
    "shuffle": False, "include_courses": [], "exclude_courses": [],
    "execution_timeout": 28800,
    "node_concurrency": 2,
    "work": False, "exam": False,
    "answer_mode": "off", "submit_mode": "save",
}


def rules_with_defaults(value=None):
    return DEFAULT_RULES | (value or {})


def course_selected(course, rules):
    identifiers = {str(course["remote_id"]), course["title"]}
    included, excluded = rules["include_courses"], rules["exclude_courses"]
    return (not included or bool(identifiers.intersection(included))) and not identifiers.intersection(excluded)


def job_enabled(kind, rules):
    if kind == "video":
        return rules["video_mode"] != "off"
    if kind in ("workid", "work", "quiz"):
        return rules["chapter_test"]
    return rules.get(kind, True)


def task_slots(task):
    import json
    rules = rules_with_defaults(json.loads(task["checkpoint"]).get("options"))
    return rules["node_concurrency"] + 1 if task["kind"] == "study" and rules["video_mode"] == "multi_node" else 1

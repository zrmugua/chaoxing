"""Answer provider selection and exact answer normalization."""
import json
import re

from .adapters.contracts import AdapterError
from .ai import preview_answer
from .question_bank import lookup


def normalize_answer(raw, question):
    """Ambiguous answers remain empty; never guess the nearest option."""
    if not question.get("supported", False):
        return []
    if isinstance(raw, str):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [s.strip() for s in re.split(r"\n|#", raw) if s.strip()]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw or not all(isinstance(s, str) and s.strip() for s in raw):
        return []
    answers = [s.strip() for s in raw]
    code, options = question.get("code"), question.get("options", [])
    if code in ("0", "1"):
        if len(answers) == 1 and re.fullmatch(r"[A-N]+", answers[0]) and answers[0] not in options:
            answers = list(answers[0])
        resolved = []
        for value in answers:
            if value in options:
                match = value
            elif re.fullmatch(r"[A-N]", value) and ord(value) - 65 < len(options):
                match = options[ord(value) - 65]
            else:
                return []
            if match not in resolved:
                resolved.append(match)
        return resolved if resolved and (code == "1" or len(resolved) == 1) else []
    if code == "3":
        if len(answers) != 1:
            return []
        value = {"正确": "正确", "错误": "错误", "true": "正确", "false": "错误",
                 "对": "正确", "错": "错误", "√": "正确", "×": "错误"}.get(answers[0].lower())
        return [value] if value else []
    if code == "2":
        return answers if question.get("blanks", 0) > 0 and len(answers) == question["blanks"] else []
    return answers if code in ("4", "6") and len(answers) == 1 else []


def resolve_answer(service, adapter, course, question, mode):
    options = question.get("options", [])
    if not question.get("supported"):
        return []
    if mode == "ai":
        raw = preview_answer(service.ai_settings(True), question["title"], options, structured=True)
    elif mode == "question_bank":
        bank = service.secret_settings("question_bank", True)
        try:
            raw = lookup(bank, question["title"], options, question["type"])
        except AdapterError:
            if not bank["ai_fallback"]:
                return []
            raw = preview_answer(service.ai_settings(True), question["title"], options, structured=True)
    elif mode == "chaoxing_ai":
        raw = adapter.chaoxing_answer(course, question)
    else:
        return []
    return normalize_answer(raw, question)

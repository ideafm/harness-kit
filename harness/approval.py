import hashlib
import json
import re
import time


MODES = ("auto", "approve-plan")
PLAN_FIELDS = ("request", "base", "specification", "plan", "criteria", "files",
               "plan_summary", "risk", "scope", "approval_reason", "plan_generation")


def validate_mode(mode):
    if mode not in MODES:
        raise ValueError("Режим должен быть auto или approve-plan")


def requires_approval(data):
    if not any(key in data for key in ("approval_mode", "effective_approval", "plan_version", "risk")):
        return False
    if data.get("approval_mode", "auto") == "approve-plan" or data.get("effective_approval") == "approve-plan":
        return True
    if data.get("risk", "low") != "low" or data.get("scope", "small") != "small":
        return True
    request = data["request"].lower()
    if re.search(r"согласу[йя]|утвер[дж]|сначала.{0,30}(?:покажи|обсудим)|approve.{0,15}plan|approval required", request):
        return True
    critical = re.compile(r"(^|/)(harness|migrations?|auth|security|infra|terraform|deploy)(/|[._-]|$)", re.I)
    return any(critical.search(name) for name in data.get("files", []))


def version(data):
    text = json.dumps({key: data.get(key) for key in PLAN_FIELDS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def verify_documents(store, task):
    data = task["data"]
    if data.get("plan_version") != version(data):
        raise ValueError("Версия плана изменилась; требуется повторное планирование")
    folder = store.folder(task["id"])
    for filename, expected in (("specification.md", data["specification"] + "\n"),
                               ("plan.md", data["plan"] + "\n"), ("summary.txt", data["published_summary"])):
        path = folder / filename
        if path.is_symlink() or not path.is_file() or path.read_text() != expected:
            raise ValueError("Документы плана изменились; требуется повторное планирование")


def approve(store, ident, expected_version, confirmation):
    task = store.get(ident)
    data = task["data"]
    if task["state"] != "awaiting_approval" or confirmation != f"TASK-{ident:03}":
        raise ValueError("Нужен ожидающий утверждения план и --confirm TASK-NNN")
    verify_documents(store, task)
    if expected_version != data["plan_version"]:
        raise ValueError("Указана устаревшая версия плана")
    data["plan_approval"] = {"version": expected_version, "time": time.time()}
    task["state"] = "queued"
    store.save(task, "plan_approved", data["plan_approval"], expected="awaiting_approval", expected_updated=task["updated"])


def revise(store, ident, feedback):
    task = store.get(ident)
    data = task["data"]
    if task["state"] != "awaiting_approval" or not isinstance(feedback, str) or not feedback.strip() or len(feedback) > 50000:
        raise ValueError("Нужен ожидающий утверждения план и замечания до 50000 символов")
    if data.get("attempts", {}).get("implement", 0):
        raise ValueError("Реализация уже начиналась; возврат требует отдельного разбора")
    data["plan_feedback"] = feedback
    data.pop("plan_approval", None)
    data["attempts"]["plan"] = 0
    task["state"], task["stage"] = "queued", "plan"
    store.save(task, "plan_revision_requested", {"version": data.get("plan_version"), "feedback": feedback},
               expected="awaiting_approval", expected_updated=task["updated"])

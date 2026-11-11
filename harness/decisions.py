def decide(store, ident, action, text, confirmation=None):
    if action not in {"request-changes", "reject"}:
        raise ValueError("Недопустимое решение")
    if not isinstance(text, str) or not text.strip() or len(text) > 50000:
        raise ValueError("Нужны замечания или причина до 50000 символов")
    task = store.get(ident)
    data = task["data"]
    if task["state"] != "review" or task["stage"] != "done":
        raise ValueError("Решение возможно только для результата на приёмке")
    if action == "reject" and confirmation != f"TASK-{ident:03}":
        raise ValueError("Нужно точное --confirm TASK-NNN")
    detail = {"text": text, "previous_verdict": data.get("review_verdict"),
              "previous_attempts": dict(data["attempts"])}
    if action == "request-changes":
        data["feedback"] = "Замечания пользователя:\n" + text
        data['result_feedback'] = text
        data["attempts"] = {**data["attempts"], "implement": 0, "check": 0, "review": 0}
        data.pop("review_verdict", None)
        data.pop("implementation_summary", None)
        task["state"], task["stage"] = "queued", "check" if data.get('verification_only') else "implement"
    else:
        data["reason"] = text
        task["state"] = "rejected"
        from .git_results import remove_worktree
        remove_worktree(store, ident)
    store.save(task, "changes_requested" if action == "request-changes" else "rejected", detail,
               expected="review", expected_updated=task["updated"])

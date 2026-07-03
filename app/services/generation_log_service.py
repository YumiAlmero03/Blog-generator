import json


def parse_generation_log(raw) -> list[dict]:
    if isinstance(raw, list):
        items = raw
    else:
        try:
            items = json.loads(raw or "[]")
        except (TypeError, json.JSONDecodeError):
            items = []
    if not isinstance(items, list):
        return []

    log_entries = []
    for item in items[-80:]:
        if not isinstance(item, dict):
            continue
        kind = _clean_generation_log_text(item.get("kind", "status")) or "status"
        message = _clean_generation_log_text(item.get("message", ""))
        if message:
            log_entries.append({"kind": kind, "message": message})
    return log_entries


def append_generation_log(log_entries: list[dict], kind: str, message: str) -> None:
    cleaned_message = _clean_generation_log_text(message)
    if not cleaned_message:
        return
    cleaned_kind = _clean_generation_log_text(kind) or "status"
    previous = log_entries[-1] if log_entries else None
    if previous and previous.get("kind") == cleaned_kind and previous.get("message") == cleaned_message:
        return
    log_entries.append({"kind": cleaned_kind, "message": cleaned_message})
    del log_entries[:-80]


def generation_log_json(log_entries: list[dict]) -> str:
    return json.dumps(parse_generation_log(log_entries), ensure_ascii=True)


def _clean_generation_log_text(value: str) -> str:
    return str(value or "").replace("\x00", "").strip()

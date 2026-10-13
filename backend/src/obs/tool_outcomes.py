"""Recognize explicit user refusals, without treating cancellation or execution errors as refusals."""
import json
import re

_USER_DECLINED = re.compile(
    r"^(?:error:\s*)?(?:user (?:rejected|declined|denied)(?: (?:the )?(?:tool|command|execution|request))?"
    r"|(?:exec command|tool execution|tool call|command|request)(?: was)? (?:rejected|declined|denied) by (?:the )?user"
    r"|aborted by user(?: after \d+(?:\.\d+)?s)?\s*$"
    r"|the user (?:doesn't|does not) want to proceed with this tool use)", re.I,
)


def user_declined(value) -> bool:
    if isinstance(value, str):
        if _USER_DECLINED.match(value.strip()):
            return True
        # Exec envelopes may contain one structured result per line. Do not scan
        # arbitrary nested command output for quoted rejection examples.
        for line in value.splitlines():
            try:
                item = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(item, str) and user_declined(item):
                return True
        return False
    if isinstance(value, list):
        return any(user_declined(item) for item in value)
    if not isinstance(value, dict):
        return False
    if value.get("userDecision") in ("rejected", "declined", "denied"):
        return True
    if value.get("status") in ("user_declined", "user_rejected"):
        return True
    for key in ("error", "message", "reason"):
        if isinstance(value.get(key), str) and _USER_DECLINED.match(value[key].strip()):
            return True
    for key in ("value", "structuredContent", "metadata"):
        if user_declined(value.get(key)):
            return True
    content = value.get("content")
    if isinstance(content, list):
        return any(block.get("type") == "text" and user_declined(block.get("text"))
                   for block in content if isinstance(block, dict))
    return False

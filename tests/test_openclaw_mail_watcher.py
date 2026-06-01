from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path("scripts/fleet/openclaw_mail_watcher.py")
    spec = importlib.util.spec_from_file_location("openclaw_mail_watcher", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_json_rpc_response_accepts_event_stream_payload() -> None:
    watcher = _load_module()
    raw = 'event: message\ndata: {"jsonrpc":"2.0","result":{"content":[{"text":"[]"}]}}\n\n'

    parsed = watcher.parse_json_rpc_response(raw)

    assert parsed["jsonrpc"] == "2.0"
    assert watcher.tool_payload(parsed) == []


def test_lifecycle_watch_line_contains_attention_rule() -> None:
    watcher = _load_module()

    line = watcher.MailWatcher.watch_line(
        {
            "id": 42,
            "subject_agent": "chris-vps",
            "supervisor_agent": "felix-m4",
            "phase": "clear",
            "status": "ready",
            "next_action": "resume gate",
            "overdue": True,
        }
    )

    assert "[LIFECYCLE OVERDUE]" in line
    assert "chris-vps supervised by felix-m4" in line
    assert "Notify companion before clear" in line
    assert "2.5-minute watch" in line

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    return _load_script("openclaw_mail_watcher", Path("scripts/fleet/openclaw_mail_watcher.py"))


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
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


def test_pane_say_watcher_lifecycle_notice_contains_attention_rule() -> None:
    watcher = _load_script("pane_say_mail_watcher", Path("scripts/fleet/pane_say_mail_watcher.py"))

    line = watcher.lifecycle_notice(
        {
            "id": 43,
            "subject_agent": "sage-zima",
            "supervisor_agent": "felix-m4",
            "phase": "verification",
            "status": "active",
            "next_action": "watch proof",
            "overdue": False,
        }
    )

    assert line.startswith("[LIFECYCLE]")
    assert "sage-zima supervised by felix-m4" in line
    assert "Notify companion before clear" in line
    assert "2.5-minute watch" in line

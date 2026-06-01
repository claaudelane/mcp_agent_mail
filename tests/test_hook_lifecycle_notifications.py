from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _fake_curl(tmp_path: Path) -> Path:
    curl_path = tmp_path / "curl"
    curl_path.write_text(
        """#!/usr/bin/env bash
body=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-d" ]]; then
    shift
    body="$1"
  fi
  shift || true
done
if [[ "$body" == *"list_lifecycle_watches"* ]]; then
  cat <<'JSON'
{"jsonrpc":"2.0","id":"2","result":{"structuredContent":{"result":{"project_key":"/fleet","count":1,"overdue_count":1,"watches":[{"subject_agent":"felix-m4","supervisor_agent":"frances-m4","phase":"ready_for_clear","status":"active","next_action":"clear and resume","overdue":true}]}}}}
JSON
else
  cat <<'JSON'
{"jsonrpc":"2.0","id":"1","result":{"structuredContent":{"result":[]}}}
JSON
fi
""",
        encoding="utf-8",
    )
    curl_path.chmod(curl_path.stat().st_mode | stat.S_IXUSR)
    return curl_path


def _hook_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}:{env['PATH']}",
            "AGENT_MAIL_PROJECT": "/fleet",
            "AGENT_MAIL_AGENT": "felix-m4",
            "AGENT_MAIL_URL": "http://127.0.0.1:7778/mcp",
            "AGENT_MAIL_TOKEN": "transport-token",
            "AGENT_MAIL_REGISTRATION_TOKEN": "agent-token",
            "AGENT_MAIL_INTERVAL": "0",
        }
    )
    return env


def test_check_inbox_reports_lifecycle_watch(tmp_path: Path) -> None:
    _fake_curl(tmp_path)
    script = Path("scripts/hooks/check_inbox.sh")

    result = subprocess.run(
        ["bash", str(script)],
        cwd=Path(__file__).resolve().parents[1],
        env=_hook_env(tmp_path),
        text=True,
        capture_output=True,
        check=True,
    )

    assert "AGENT MAIL REMINDER" in result.stdout
    assert "active lifecycle watch" in result.stdout
    assert "felix-m4 supervised by frances-m4" in result.stdout
    assert "do not drift while a partner is waiting" in result.stdout


def test_codex_notify_reports_lifecycle_watch(tmp_path: Path) -> None:
    _fake_curl(tmp_path)
    script = Path("scripts/hooks/codex_notify.sh")

    result = subprocess.run(
        ["bash", str(script), "{}"],
        cwd=Path(__file__).resolve().parents[1],
        env=_hook_env(tmp_path),
        text=True,
        capture_output=True,
        check=True,
    )

    assert "AGENT MAIL REMINDER" in result.stdout
    assert "active lifecycle watch" in result.stdout
    assert "felix-m4 supervised by frances-m4" in result.stdout
    assert "do not drift while a partner is waiting" in result.stdout

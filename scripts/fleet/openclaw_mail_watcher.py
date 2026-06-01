#!/usr/bin/env python3
"""Poll MCP Agent Mail and inject fleet notices into an OpenClaw tmux pane."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_ENV_PATH = "~/.config/mcp-agent-mail/.env"
DEFAULT_POLL_SECONDS = 20


def load_env(path: str) -> dict[str, str]:
    env_path = Path(path).expanduser()
    values: dict[str, str] = {}
    with env_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.replace("export ", "").strip()] = value.strip().strip("'\"")
    return values


def first_env(values: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = values.get(name) or os.environ.get(name)
        if value:
            return value
    return default


def parse_json_rpc_response(raw: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        raw = match.group(0)
    return json.loads(raw)


def tool_payload(response: dict[str, Any]) -> Any:
    result = response.get("result", {})
    if result.get("isError"):
        return None
    structured = result.get("structuredContent", {})
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        text = content[0].get("text") or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return None


class MailWatcher:
    def __init__(self, env: dict[str, str]) -> None:
        self.project = first_env(env, "AGENT_MAIL_PROJECT", "MCP_AGENT_MAIL_PROJECT_KEY")
        self.agent = first_env(env, "AGENT_MAIL_AGENT", "MCP_AGENT_MAIL_AGENT_NAME")
        self.url = first_env(env, "AGENT_MAIL_URL", "MCP_AGENT_MAIL_URL")
        self.bearer = first_env(env, "AGENT_MAIL_TOKEN", "HTTP_BEARER_TOKEN")
        self.registration_token = first_env(env, "AGENT_MAIL_REGISTRATION_TOKEN", "CHRIS_VPS_REGISTRATION_TOKEN")
        self.tmux_target = first_env(env, "MCP_AGENT_MAIL_PANE_TARGET", "TMUX_TARGET", default="chris")
        self.poll_seconds = int(first_env(env, "MCP_AGENT_MAIL_POLL_SECONDS", "AGENT_MAIL_POLL_SECONDS", default=str(DEFAULT_POLL_SECONDS)))
        self.inbox_high_water = 0
        self.watch_keys_seen: set[str] = set()

    def validate(self) -> None:
        missing = [
            name
            for name, value in {
                "project": self.project,
                "agent": self.agent,
                "url": self.url,
                "bearer": self.bearer,
                "registration_token": self.registration_token,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"missing required config: {', '.join(missing)}")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.bearer}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        raw = urllib.request.urlopen(request, timeout=20).read().decode()
        return tool_payload(parse_json_rpc_response(raw))

    def inbox(self) -> list[dict[str, Any]]:
        payload = self.call_tool(
            "fetch_inbox",
            {
                "project_key": self.project,
                "agent_name": self.agent,
                "registration_token": self.registration_token,
                "limit": 10,
                "include_bodies": False,
            },
        )
        return payload if isinstance(payload, list) else []

    def lifecycle_watches(self) -> list[dict[str, Any]]:
        payload = self.call_tool(
            "list_lifecycle_watches",
            {
                "project_key": self.project,
                "agent_name": self.agent,
                "active_only": True,
                "limit": 20,
            },
        )
        if not isinstance(payload, dict):
            return []
        watches = payload.get("watches")
        return watches if isinstance(watches, list) else []

    def session_alive(self) -> bool:
        return subprocess.run(["tmux", "has-session", "-t", self.tmux_target], capture_output=True, check=False).returncode == 0

    def inject(self, line: str) -> None:
        if not self.session_alive():
            return
        subprocess.run(["tmux", "send-keys", "-t", self.tmux_target, "-l", line], check=False)
        time.sleep(0.5)
        subprocess.run(["tmux", "send-keys", "-t", self.tmux_target, "Enter"], check=False)

    @staticmethod
    def message_id(message: dict[str, Any]) -> int:
        try:
            return int(message.get("id", 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def watch_key(watch: dict[str, Any]) -> str:
        fields = [
            watch.get("id"),
            watch.get("session_id"),
            watch.get("phase"),
            watch.get("status"),
            watch.get("next_action"),
            watch.get("updated_ts"),
            watch.get("overdue"),
        ]
        return json.dumps(fields, sort_keys=True, default=str)

    @staticmethod
    def watch_line(watch: dict[str, Any]) -> str:
        subject = watch.get("subject_agent") or "unknown"
        supervisor = watch.get("supervisor_agent") or "unknown"
        phase = watch.get("phase") or "watching"
        status = watch.get("status") or "active"
        next_action = watch.get("next_action") or "keep lifecycle attention tight"
        overdue = " OVERDUE" if watch.get("overdue") else ""
        return (
            f"[LIFECYCLE{overdue}] {subject} supervised by {supervisor}: "
            f"{phase}/{status}. {next_action}. Notify companion before clear; keep 2.5-minute watch tight."
        )

    def initialize(self) -> None:
        self.inbox_high_water = max([self.message_id(message) for message in self.inbox()] + [0])
        self.watch_keys_seen = {self.watch_key(watch) for watch in self.lifecycle_watches()}
        print(
            f"[openclaw-mail-watcher] up agent={self.agent} inbox_high_water={self.inbox_high_water} "
            f"active_watches={len(self.watch_keys_seen)} poll={self.poll_seconds}s",
            flush=True,
        )

    def run_once(self) -> None:
        for message in sorted(self.inbox(), key=self.message_id):
            message_id = self.message_id(message)
            if message_id <= self.inbox_high_water:
                continue
            sender = message.get("sender_name") or message.get("from") or "?"
            subject = (message.get("subject") or "(no subject)")[:80]
            self.inject(f"[MAIL] new fleet mail from {sender}: \"{subject}\" (id {message_id}). Run fetch_inbox to read + act per your charter.")
            self.inbox_high_water = message_id
            print(f"[openclaw-mail-watcher] injected mail id={message_id} from={sender}", flush=True)

        for watch in self.lifecycle_watches():
            key = self.watch_key(watch)
            if key in self.watch_keys_seen:
                continue
            self.inject(self.watch_line(watch))
            self.watch_keys_seen.add(key)
            print(f"[openclaw-mail-watcher] injected lifecycle watch id={watch.get('id')}", flush=True)

    def run(self) -> None:
        self.validate()
        self.initialize()
        while True:
            try:
                self.run_once()
            except Exception as exc:
                print(f"[openclaw-mail-watcher] WARN {exc}", flush=True)
            time.sleep(self.poll_seconds)


def main() -> None:
    env_path = os.environ.get("MCP_AGENT_MAIL_ENV_FILE", DEFAULT_ENV_PATH)
    MailWatcher(load_env(env_path)).run()


if __name__ == "__main__":
    main()

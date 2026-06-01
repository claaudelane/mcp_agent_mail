#!/usr/bin/env python3
"""mcp_agent_mail watcher with separate mailbox identity and pane target."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MCP_URL_DEFAULT = "http://127.0.0.1:7778/mcp"


def _parse_jsonrpc(raw: str) -> dict:
    m = re.search(r"data:\s*(\{.*\})", raw, re.DOTALL)
    body = m.group(1) if m else raw
    return json.loads(body)


def _mcp_call(mcp_url: str, transport_bearer: str, tool: str, args: dict, req_id: int = 1) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
        "id": req_id,
    }
    res = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "POST",
            mcp_url,
            "-H",
            f"Authorization: Bearer {transport_bearer}",
            "-H",
            "Content-Type: application/json",
            "-H",
            "Accept: application/json,text/event-stream",
            "-d",
            json.dumps(payload),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return _parse_jsonrpc(res.stdout)


def fetch_inbox_unread(
    mcp_url: str,
    transport_bearer: str,
    project_key: str,
    agent_name: str,
    registration_token: str,
) -> list[dict]:
    d = _mcp_call(
        mcp_url,
        transport_bearer,
        "fetch_inbox",
        {
            "project_key": project_key,
            "agent_name": agent_name,
            "registration_token": registration_token,
            "include_bodies": False,
            "limit": 20,
            "unread_only": True,
        },
        req_id=1,
    )
    sc = d.get("result", {}).get("structuredContent", {})
    return sc.get("result", []) if isinstance(sc, dict) else []


def mark_read(
    mcp_url: str,
    transport_bearer: str,
    project_key: str,
    agent_name: str,
    registration_token: str,
    message_id: int,
) -> bool:
    try:
        d = _mcp_call(
            mcp_url,
            transport_bearer,
            "mark_message_read",
            {
                "project_key": project_key,
                "agent_name": agent_name,
                "registration_token": registration_token,
                "message_id": message_id,
            },
            req_id=2,
        )
        sc = d.get("result", {}).get("structuredContent", {})
        return bool(sc.get("read"))
    except Exception:
        return False


def _tool_payload(response: dict) -> object:
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
        except Exception:
            return text
    return None


def fetch_lifecycle_watches(
    mcp_url: str,
    transport_bearer: str,
    project_key: str,
    agent_name: str,
) -> list[dict]:
    d = _mcp_call(
        mcp_url,
        transport_bearer,
        "list_lifecycle_watches",
        {
            "project_key": project_key,
            "agent_name": agent_name,
            "active_only": True,
            "limit": 20,
        },
        req_id=3,
    )
    payload = _tool_payload(d)
    watches = payload.get("watches") if isinstance(payload, dict) else []
    return watches if isinstance(watches, list) else []


def lifecycle_watch_key(watch: dict) -> str:
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


def lifecycle_notice(watch: dict) -> str:
    subject = watch.get("subject_agent") or "unknown"
    supervisor = watch.get("supervisor_agent") or "unknown"
    phase = watch.get("phase") or "watching"
    status = watch.get("status") or "active"
    next_action = watch.get("next_action") or "keep lifecycle attention tight"
    overdue = " OVERDUE" if watch.get("overdue") else ""
    return (
        f"[LIFECYCLE{overdue}] {subject} supervised by {supervisor}: "
        f"{phase}/{status}. {next_action}. Notify companion before clear; "
        "keep 2.5-minute watch tight."
    )


def inject_notice(target_agent: str, notice: str) -> bool:
    try:
        subprocess.run(
            ["pane-say-agent", target_agent, notice],
            check=True,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def watch(
    signal_path: Path,
    mcp_url: str,
    transport_bearer: str,
    project_key: str,
    agent_name: str,
    pane_target: str,
    registration_token: str,
    poll_seconds: float,
    heartbeat_seconds: float,
    standdown_flag: Path | None = None,
) -> None:
    last_signal_mtime: float | None = None
    last_heartbeat = time.monotonic()
    seen_lifecycle_watches = {
        lifecycle_watch_key(watch)
        for watch in fetch_lifecycle_watches(
            mcp_url,
            transport_bearer,
            project_key,
            agent_name,
        )
    }
    standdown_announced = False
    print(
        f"[watcher] up. signal={signal_path} agent={agent_name} pane_target={pane_target} "
        f"poll={poll_seconds}s heartbeat={heartbeat_seconds}s standdown_flag={standdown_flag} "
        f"active_lifecycle_watches={len(seen_lifecycle_watches)}",
        flush=True,
    )
    while True:
        if standdown_flag and standdown_flag.exists():
            if not standdown_announced:
                print(
                    f"[watcher] standdown active (flag={standdown_flag}) - messages queue, no notifications fire",
                    flush=True,
                )
                standdown_announced = True
            time.sleep(poll_seconds)
            continue
        if standdown_announced:
            print("[watcher] standdown lifted - resuming notifications", flush=True)
            standdown_announced = False
            last_signal_mtime = None
            last_heartbeat = time.monotonic() - heartbeat_seconds

        triggered_by = None
        try:
            stat = signal_path.stat()
            mtime = stat.st_mtime
            if last_signal_mtime is None or mtime > last_signal_mtime:
                triggered_by = "signal"
                last_signal_mtime = mtime
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[watcher] signal stat error: {e}", flush=True)

        if triggered_by is None:
            elapsed = time.monotonic() - last_heartbeat
            if elapsed >= heartbeat_seconds:
                triggered_by = "heartbeat"

        if triggered_by:
            try:
                msgs = fetch_inbox_unread(
                    mcp_url,
                    transport_bearer,
                    project_key,
                    agent_name,
                    registration_token,
                )
                last_heartbeat = time.monotonic()
                last_signal_mtime = None
                for msg in msgs:
                    sender = msg.get("from", "?")
                    subject = msg.get("subject", "<no subject>")
                    importance = msg.get("importance", "normal")
                    mid = msg.get("id", "?")
                    notice = (
                        f"[MAIL] from={sender} to={agent_name} "
                        f"subject={subject!r} importance={importance} "
                        f"id={mid} via=mcp_agent_mail"
                    )
                    ok = inject_notice(pane_target, notice)
                    marked = False
                    if ok and isinstance(mid, int):
                        marked = mark_read(
                            mcp_url,
                            transport_bearer,
                            project_key,
                            agent_name,
                            registration_token,
                            mid,
                        )
                    print(
                        f"[watcher] {triggered_by}: msg id={mid} from={sender} "
                        f"inject={'ok' if ok else 'FAIL'} marked={'ok' if marked else 'no'}",
                        flush=True,
                    )
                if not msgs:
                    print(f"[watcher] {triggered_by}: 0 unread", flush=True)
                watches = fetch_lifecycle_watches(
                    mcp_url,
                    transport_bearer,
                    project_key,
                    agent_name,
                )
                injected = 0
                for watch_item in watches:
                    key = lifecycle_watch_key(watch_item)
                    if key in seen_lifecycle_watches:
                        continue
                    ok = inject_notice(pane_target, lifecycle_notice(watch_item))
                    seen_lifecycle_watches.add(key)
                    injected += 1 if ok else 0
                    print(
                        f"[watcher] {triggered_by}: lifecycle id={watch_item.get('id')} "
                        f"inject={'ok' if ok else 'FAIL'}",
                        flush=True,
                    )
                if not watches:
                    seen_lifecycle_watches.clear()
                elif not injected:
                    print(f"[watcher] {triggered_by}: 0 new lifecycle watches", flush=True)
            except Exception as e:
                print(f"[watcher] fetch error: {e}", flush=True)

        time.sleep(poll_seconds)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--signal-path", required=True, type=Path)
    p.add_argument("--mcp-url", default=MCP_URL_DEFAULT)
    p.add_argument("--transport-bearer-env", default="HTTP_BEARER_TOKEN")
    p.add_argument("--project-key", required=True)
    p.add_argument("--agent-name", required=True, help="mcp_agent_mail identity, e.g. felix-zima")
    p.add_argument("--pane-target", default=None, help="pane-say-agent route, e.g. Felix-Zima")
    p.add_argument("--registration-token-env", required=True)
    p.add_argument("--poll-seconds", type=float, default=5.0)
    p.add_argument("--heartbeat-seconds", type=float, default=1800.0)
    p.add_argument("--standdown-flag", type=Path, default=None)
    args = p.parse_args(argv)

    bearer = os.environ.get(args.transport_bearer_env, "").strip()
    token = os.environ.get(args.registration_token_env, "").strip()
    if not bearer:
        print(f"[watcher] FATAL: env {args.transport_bearer_env} empty/missing", file=sys.stderr)
        return 2
    if not token:
        print(f"[watcher] FATAL: env {args.registration_token_env} empty/missing", file=sys.stderr)
        return 2

    pane_target = args.pane_target or args.agent_name
    try:
        watch(
            signal_path=args.signal_path,
            mcp_url=args.mcp_url,
            transport_bearer=bearer,
            project_key=args.project_key,
            agent_name=args.agent_name,
            pane_target=pane_target,
            registration_token=token,
            poll_seconds=args.poll_seconds,
            heartbeat_seconds=args.heartbeat_seconds,
            standdown_flag=args.standdown_flag,
        )
    except KeyboardInterrupt:
        print("[watcher] shutdown", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

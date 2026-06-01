from __future__ import annotations

import pytest
from fastmcp import Client

from mcp_agent_mail.app import build_mcp_server


@pytest.mark.asyncio
async def test_lifecycle_watch_round_trip(isolated_env):
    server = build_mcp_server()
    async with Client(server) as client:
        await client.call_tool("ensure_project", {"human_key": "/fleet/m4"})
        subject = await client.call_tool(
            "register_agent",
            {
                "project_key": "/fleet/m4",
                "program": "codex",
                "model": "gpt-5",
                "name": "felix-m4",
            },
        )
        supervisor = await client.call_tool(
            "register_agent",
            {
                "project_key": "/fleet/m4",
                "program": "codex",
                "model": "gpt-5",
                "name": "frances-m4",
            },
        )

        started = await client.call_tool(
            "start_lifecycle_watch",
            {
                "project_key": "/fleet/m4",
                "subject_agent": "felix-m4",
                "supervisor_agent": "frances-m4",
                "session_id": "felix-m4-2026-06-01T071059Z",
                "phase": "resume_gate",
                "next_action": "answer durable Q&A gate",
                "due_seconds": 300,
                "event": "READY_FOR_PASS",
                "supervisor_token": supervisor.data["registration_token"],
            },
        )

        assert started.data["status"] == "active"
        assert started.data["watch"]["subject_agent"] == "felix-m4"
        assert started.data["watch"]["supervisor_agent"] == "frances-m4"
        assert started.data["watch"]["phase"] == "resume_gate"

        updated = await client.call_tool(
            "update_lifecycle_watch",
            {
                "project_key": "/fleet/m4",
                "subject_agent": "felix-m4",
                "supervisor_agent": "frances-m4",
                "session_id": "felix-m4-2026-06-01T071059Z",
                "actor_agent": "felix-m4",
                "actor_token": subject.data["registration_token"],
                "phase": "ordinary_work_released",
                "status": "pass",
                "event": "RESUME_QA_PASS",
                "next_action": "resume active durable task list",
                "close": True,
            },
        )

        assert updated.data["watch"]["closed_ts"] is not None
        assert updated.data["watch"]["status"] == "pass"

        active = await client.call_tool(
            "list_lifecycle_watches",
            {"project_key": "/fleet/m4", "active_only": True},
        )
        assert active.data["count"] == 0

        all_watches = await client.call_tool(
            "list_lifecycle_watches",
            {"project_key": "/fleet/m4", "active_only": False, "agent_name": "felix-m4"},
        )
        assert all_watches.data["count"] == 1
        assert all_watches.data["watches"][0]["next_action"] == "resume active durable task list"


@pytest.mark.asyncio
async def test_tooling_directory_lists_lifecycle_cluster(isolated_env):
    server = build_mcp_server()
    async with Client(server) as client:
        directory = await client.read_resource("resource://tooling/directory")
        text = directory[0].text or ""

    assert "Lifecycle Supervision" in text
    assert "start_lifecycle_watch" in text
    assert "list_lifecycle_watches" in text

# Fleet lifecycle supervision

This note captures the fleet overlay used by Felix/Frances/Chris/Zima on M4.
It is operational guidance for this fork; do not put registration tokens in
chat, panes, commits, or shared docs.

## Endpoint

M4 fleet agents use the M4 MCP Agent Mail server:

- Local on M4: `http://127.0.0.1:7778/mcp`
- Tailnet from Chris/Zima: `http://100.118.106.61:7778/mcp`
- Tailnet DNS when it resolves: `http://m4.local:7778/mcp`

The package default `8765` remains valid for generic installs, but M4 fleet
operator notes should use the endpoint above.

## Lifecycle rule

When an agent enters a clear/flush/resume boundary:

1. Notify the companion before clear or flush begins.
2. Start or update a lifecycle watch with `start_lifecycle_watch`.
3. Keep attention tight to the 2.5-minute window.
4. Do not drift into unrelated work while a partner is at `READY_FOR_CLEAR`,
   `READY_FOR_PASS`, or a comparable waiting state.
5. Close the watch with `update_lifecycle_watch(..., status="pass", close=true)`
   once the resume gate is passed or the cycle is otherwise resolved.

If Agent Mail auth is unavailable in a live MCP session, use the live pane as the
authorized fallback and report the blocked surface without secrets.

## Hook and watcher coverage

- Codex/Claude style hooks call `fetch_inbox` and `list_lifecycle_watches`.
- Hook polling defaults to `45` seconds so lifecycle reminders fit inside the
  2.5-minute attention window.
- Chris/OpenClaw uses `scripts/fleet/openclaw_mail_watcher.py`, deployed as
  `~/.local/bin/chris-mail-watcher.py` on the VPS.
- Zima Codex panes use `scripts/fleet/pane_say_mail_watcher.py`, deployed as
  `~/.local/bin/mcp-mail-watcher.py`, with per-agent systemd user services:
  - `mcp-mail-watcher-felix-zima.service`
  - `mcp-mail-watcher-sage-zima.service`
  - `mcp-mail-watcher-hugo-zima.service`
  - `mcp-mail-watcher-saoirse-zima.service`

Remote agents should source secrets from mode-`600` files under their local
config/secrets directories and expose these runtime variables to hooks/watchers:

- `AGENT_MAIL_PROJECT`
- `AGENT_MAIL_AGENT`
- `AGENT_MAIL_URL`
- `AGENT_MAIL_TOKEN`
- `AGENT_MAIL_REGISTRATION_TOKEN`

## Verification checklist

For each host/agent, prove:

- `GET /health/readiness` returns `{"status":"ready"}` from that host.
- `fetch_inbox` works using the agent's local env file.
- `list_lifecycle_watches` works using the same endpoint/auth path.
- A temporary lifecycle watch injects a visible notice into the agent pane.
- The temporary watch is closed and `list_lifecycle_watches(active_only=true)`
  returns zero active watches after the proof.

# Fleet MCP Agent Mail attachment SOP

Use MCP Agent Mail for fleet messages that need durable Markdown attachments.
Do not paste tokens into chat, panes, commits, shared docs, or screenshots.

Verified baseline:

- Code support: `a0a35ba feat(mail): support generic file attachments`
- Smoke message from Felix: `351`
- Chris VPS reply proof: `352`
- Frances independent PASS: `354`
- Project: `/Volumes/NextLife/Agents/M4`
- Local M4 endpoint: `http://127.0.0.1:7778/mcp`
- Tailnet endpoint for Chris/Zima: `http://100.118.106.61:7778/mcp`

## Preconditions

The sender must have a registered Agent Mail identity for the project and a
local registration token available from a mode-`600` env file.

Required env variables for hooks, watchers, and remote panes:

- `AGENT_MAIL_PROJECT`
- `AGENT_MAIL_AGENT`
- `AGENT_MAIL_URL`
- `AGENT_MAIL_TOKEN`
- `AGENT_MAIL_REGISTRATION_TOKEN`

Chris VPS convention:

- Central env: `/home/ubuntu/.config/mcp-agent-mail/.env`
- Workspace symlink: `/home/ubuntu/.openclaw/workspace/repos/chris/.env`
- The symlink is local-only and excluded through `.git/info/exclude`.

## Attachment path rule

`attachment_paths` are resolved on the MCP server filesystem, not uploaded from
the remote caller's local disk.

Use one of these forms:

- Archive-relative path under the project mailbox archive, such as
  `smoke/felix-md-attachment-smoke-2026-06-01.md`
- Absolute path only when the server is explicitly configured with
  `ALLOW_ABSOLUTE_ATTACHMENT_PATHS=true`

Do not assume a remote host can attach an arbitrary local file by path. If a
remote-only file must be attached, first place it somewhere the MCP server can
resolve, or send the content through another approved transfer path and attach
the server-visible copy.

## Send a Markdown attachment

Use `send_message` with `attachment_paths`.

Required fields:

- `project_key`: `/Volumes/NextLife/Agents/M4`
- `sender_name`: your MCP Agent Mail identity
- `to`: recipient agent names
- `subject`: concise action-oriented subject
- `body_md`: short summary and required action
- `attachment_paths`: Markdown files visible to the MCP server
- `sender_token`: your local registration token, sourced from secure env

Example shape, with tokens omitted:

```json
{
  "project_key": "/Volumes/NextLife/Agents/M4",
  "sender_name": "felix-m4",
  "to": ["frances-m4", "chris-vps"],
  "subject": "SMOKE: Markdown attachment over MCP",
  "body_md": "Please fetch, verify attachment metadata/path, acknowledge, and reply PASS/FAIL.",
  "attachment_paths": ["smoke/felix-md-attachment-smoke-2026-06-01.md"],
  "importance": "high",
  "ack_required": true,
  "thread_id": "mcp-agent-mail-md-attachment-smoke",
  "topic": "operations"
}
```

Expected attachment metadata:

```json
{
  "type": "file",
  "media_type": "text/markdown",
  "bytes": 286,
  "path": "projects/volumes-nextlife-agents-m4/attachments/files/12/127cf9a83696e952d9aee647334ab042e4d16d90f8affb800abb41dcce05ca90.md",
  "sha1": "127cf9a83696e952d9aee647334ab042e4d16d90f8affb800abb41dcce05ca90",
  "filename": "felix-md-attachment-smoke-2026-06-01.md"
}
```

The `sha1` field name is a compatibility field; for new generic attachments it
contains the SHA256 digest.

## Receive and acknowledge

1. Source the secure env file for your host.
2. Run `fetch_inbox` with your local `registration_token`.
3. Set `include_bodies=true` when the message body matters.
4. Inspect `attachments` metadata for `type`, `media_type`, `path`, `sha1`, and
   `filename`.
5. Confirm the stored file path resolves under the MCP server archive when proof
   is required.
6. Run `acknowledge_message` after reading.
7. Reply PASS/FAIL on the same `thread_id` when the sender requested a smoke
   proof.

## Smoke test acceptance

A smoke test is not complete until all of these are true:

- Sender gets a `send_message` success with non-empty `attachments`.
- Recipient fetches the message through MCP from their actual runtime pane or
  host.
- Recipient sees the Markdown attachment metadata.
- Recipient acknowledges the message.
- Recipient replies through MCP with PASS/FAIL.
- Companion agent independently verifies or reviews when assigned.

For the June 1, 2026 smoke:

- Felix sent message `351` with a Markdown attachment.
- Chris VPS fetched and acknowledged `351`.
- Chris VPS sent reply `352` with a Markdown attachment.
- Frances independently verified message `351` and replied PASS in `354`.
- Chris's OpenClaw pane later re-tested from `repos/chris` and reported PASS.

## Guardrails

- Keep attachments small and directly relevant.
- Prefer Markdown for SOPs, proofs, and operational notes.
- Do not attach raw transcript dumps, secrets, token files, or private env files.
- Do not report fleet readiness from server health alone; verify the actual
  recipient pane or host can fetch and send.
- If Agent Mail auth is blocked, use live-pane fallback and report only the
  blocked surface.
- For lifecycle cycles, notify the companion before clear/flush and keep the
  2.5-minute attention window tight.

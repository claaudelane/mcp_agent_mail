#!/usr/bin/env bash
# Fleet mail backbone launcher (Python server). Loads local config, runs HTTP server.
set -euo pipefail
ENV_FILE="${AGENT_MAIL_ENV:-$HOME/.config/mcp-agent-mail/.env}"
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE — see Fleet Mail Backbone brief"; exit 1; }
set -a; . "$ENV_FILE"; set +a
cd "$(dirname "$0")"
exec uv run python -m mcp_agent_mail.http --host "${HTTP_HOST:-127.0.0.1}" --port "${HTTP_PORT:-8765}"

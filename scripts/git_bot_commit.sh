#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_ENV_FILE="${ROOT_DIR}/.bot.local.env"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${BOT_ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${BOT_ENV_FILE}"
  set +a
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

BOT_GIT_NAME="${BOT_GIT_NAME:-Code Assist Bot}"
BOT_GIT_EMAIL="${BOT_GIT_EMAIL:-bot@local.invalid}"

usage() {
  cat <<'EOF'
Usage:
  scripts/git_bot_commit.sh -m "<message>"
  scripts/git_bot_commit.sh --amend --no-edit
  scripts/git_bot_commit.sh -- <git commit args...>

Notes:
  - Uses one-off git config flags so repository/global git config is not changed.
  - Reads BOT_GIT_NAME and BOT_GIT_EMAIL from .bot.local.env if present.
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--" ]]; then
  shift
fi

git -c user.name="${BOT_GIT_NAME}" -c user.email="${BOT_GIT_EMAIL}" commit "$@"

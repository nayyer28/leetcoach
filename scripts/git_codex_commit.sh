#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX_ENV_FILE="${ROOT_DIR}/.codex.local.env"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${CODEX_ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${CODEX_ENV_FILE}"
  set +a
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

CODEX_GIT_NAME="${CODEX_GIT_NAME:-Codex}"
CODEX_GIT_EMAIL="${CODEX_GIT_EMAIL:-codex@local.invalid}"

usage() {
  cat <<'EOF'
Usage:
  scripts/git_codex_commit.sh -m "<message>"
  scripts/git_codex_commit.sh --amend --no-edit
  scripts/git_codex_commit.sh -- <git commit args...>

Notes:
  - Uses one-off git config flags so repository/global git config is not changed.
  - Reads CODEX_GIT_NAME and CODEX_GIT_EMAIL from .codex.local.env if present.
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

git -c user.name="${CODEX_GIT_NAME}" -c user.email="${CODEX_GIT_EMAIL}" commit "$@"

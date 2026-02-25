#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  set +a
fi

: "${GITHUB_APP_ID:?GITHUB_APP_ID is required}"
: "${GITHUB_APP_INSTALLATION_ID:?GITHUB_APP_INSTALLATION_ID is required}"
: "${GITHUB_APP_PRIVATE_KEY_PATH:?GITHUB_APP_PRIVATE_KEY_PATH is required}"

if [[ ! -f "${GITHUB_APP_PRIVATE_KEY_PATH}" ]]; then
  echo "Private key not found: ${GITHUB_APP_PRIVATE_KEY_PATH}" >&2
  exit 1
fi

b64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

make_jwt() {
  local now iat exp header payload header_b64 payload_b64 signing_input sig_b64
  now="$(date +%s)"
  iat="$((now - 60))"
  exp="$((now + 540))"

  header='{"alg":"RS256","typ":"JWT"}'
  payload="{\"iat\":${iat},\"exp\":${exp},\"iss\":\"${GITHUB_APP_ID}\"}"

  header_b64="$(printf '%s' "${header}" | b64url)"
  payload_b64="$(printf '%s' "${payload}" | b64url)"
  signing_input="${header_b64}.${payload_b64}"
  sig_b64="$(
    printf '%s' "${signing_input}" \
      | openssl dgst -binary -sha256 -sign "${GITHUB_APP_PRIVATE_KEY_PATH}" \
      | b64url
  )"

  printf '%s.%s' "${signing_input}" "${sig_b64}"
}

fetch_installation_token() {
  local jwt response token expires_at
  jwt="$(make_jwt)"

  response="$(
    curl -fsSL \
      -X POST \
      -H "Accept: application/vnd.github+json" \
      -H "Authorization: Bearer ${jwt}" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "https://api.github.com/app/installations/${GITHUB_APP_INSTALLATION_ID}/access_tokens"
  )"

  token="$(printf '%s' "${response}" | jq -r '.token')"
  expires_at="$(printf '%s' "${response}" | jq -r '.expires_at')"

  if [[ -z "${token}" || "${token}" == "null" ]]; then
    printf '%s\n' "${response}" >&2
    echo "Failed to mint installation token." >&2
    exit 1
  fi

  printf '%s\n%s\n' "${token}" "${expires_at}"
}

usage() {
  cat <<'EOF'
Usage:
  scripts/gh_app_token.sh --export
  scripts/gh_app_token.sh --print-token
  scripts/gh_app_token.sh --gh <gh args...>

Examples:
  eval "$(scripts/gh_app_token.sh --export)"
  scripts/gh_app_token.sh --gh pr create --base main --head codex/x --title "..." --body "..."
EOF
}

main() {
  local mode token expires_at out
  mode="${1:-}"

  case "${mode}" in
    --export)
      out="$(fetch_installation_token)"
      token="${out%%$'\n'*}"
      expires_at="${out#*$'\n'}"
      printf 'unset GITHUB_TOKEN\n'
      printf 'export GH_TOKEN=%q\n' "${token}"
      printf 'export GH_APP_TOKEN_EXPIRES_AT=%q\n' "${expires_at}"
      ;;
    --print-token)
      fetch_installation_token | sed -n '1p'
      ;;
    --gh)
      shift || true
      if [[ $# -eq 0 ]]; then
        usage
        exit 1
      fi
      out="$(fetch_installation_token)"
      token="${out%%$'\n'*}"
      expires_at="${out#*$'\n'}"
      echo "Using GitHub App installation token (expires ${expires_at})" >&2
      env -u GITHUB_TOKEN GH_TOKEN="${token}" gh "$@"
      ;;
    -h|--help|"")
      usage
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"

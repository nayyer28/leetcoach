# Scripts

This folder contains local developer helper scripts for the `leetcoach` repository.

## Local Codex Config

Use a repo-local `.codex.local.env` file (ignored by Git) for Codex-specific tooling configuration so values do not need to be remembered in chat context.

Bootstrap from the committed template:

```bash
cp .codex.local.env.example .codex.local.env
```

Recommended variables:

```env
CODEX_GIT_NAME=Codex
CODEX_GIT_EMAIL=codex@local.invalid
DEFAULT_PR_BASE=main
GITHUB_APP_ID=...
GITHUB_APP_INSTALLATION_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/app.private-key.pem
```

Notes:
- `.codex.local.env` is for local developer/tooling values.
- `.env` can still be used for project runtime configuration (Telegram token, DB settings, etc.).
- `scripts/gh_app_token.sh` loads `.codex.local.env` first, then `.env` as a fallback.

## `gh_app_token.sh`

`scripts/gh_app_token.sh` mints a short-lived GitHub App installation token and uses it with the GitHub CLI (`gh`).

This is used so pull requests can be created by the GitHub App identity (for example, `Codex Bot`) instead of the repository owner's personal GitHub account.

### What it does

1. Loads GitHub App config from `.codex.local.env` first, then `.env` as a fallback.
2. Creates a signed JWT using the GitHub App private key (`.pem`).
3. Exchanges that JWT for a short-lived installation access token from GitHub.
4. Either:
   - prints shell exports (`GH_TOKEN`) for your current shell, or
   - runs `gh ...` directly with the token.

### Required local configuration

Create a repo-local `.codex.local.env` file (already ignored by `.gitignore`) with:

```env
GITHUB_APP_ID=...
GITHUB_APP_INSTALLATION_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/app.private-key.pem
```

Notes:
- Do not commit `.codex.local.env`.
- The `.pem` private key should live outside the repo or in a protected local path.

### Prerequisites

The script expects these tools to be installed:

- `openssl`
- `curl`
- `jq`
- `gh` (GitHub CLI)

### Usage

Print export commands for the current shell:

```bash
eval "$(scripts/gh_app_token.sh --export)"
```

This sets:
- `GH_TOKEN` (short-lived installation token)
- `GH_APP_TOKEN_EXPIRES_AT` (timestamp)

It also unsets `GITHUB_TOKEN` in the emitted commands to avoid conflicts with a stale or invalid token.

Print only the installation token:

```bash
scripts/gh_app_token.sh --print-token
```

Run a `gh` command directly as the GitHub App installation:

```bash
scripts/gh_app_token.sh --gh pr create \
  --base main \
  --head codex/my-branch \
  --title "..." \
  --body "..."
```

### Why this exists (identity model)

There are three separate identities in the workflow:

- `git commit` author identity:
  - set with one-off flags (for example `Codex <codex@local.invalid>`)
- `git push` auth:
  - usually your machine's SSH key
- `gh` API identity (PR creator):
  - GitHub App installation token (`GH_TOKEN`)

This script only affects the third one (`gh` API identity).

## `git_codex_commit.sh`

`scripts/git_codex_commit.sh` wraps `git commit` using one-off `user.name` / `user.email` flags so repository/global Git config is not modified.

It reads these values from `.codex.local.env` (or falls back to defaults):

```env
CODEX_GIT_NAME=Codex
CODEX_GIT_EMAIL=codex@local.invalid
```

Examples:

```bash
git add README.md
scripts/git_codex_commit.sh -m "docs: update README"
```

```bash
scripts/git_codex_commit.sh --amend --no-edit
```

### Security notes

- GitHub App installation tokens are short-lived.
- Protect the GitHub App private key (`.pem`); anyone with it can mint app tokens.
- Keep app permissions minimal and scoped to selected repositories.

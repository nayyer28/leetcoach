# Scripts

This folder contains local developer helper scripts for the `leetcoach` repository.

## Local Bot Config

Use a repo-local `.bot.local.env` file (ignored by Git) for bot-specific tooling configuration so values do not need to be remembered in chat context.

Bootstrap from the committed template:

```bash
cp .bot.local.env.example .bot.local.env
```

Recommended variables:

```env
# Use the actual bot name (Claude, Codex, etc.) to identify which assistant made commits
BOT_GIT_NAME=Claude
BOT_GIT_EMAIL=claude@anthropic.com
DEFAULT_PR_BASE=main
GITHUB_APP_ID=...
GITHUB_APP_INSTALLATION_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/app.private-key.pem
```

Notes:
- `.bot.local.env` is for local developer/tooling values.
- `.env` can still be used for project runtime configuration (Telegram token, DB settings, etc.).
- `scripts/gh_app_token.sh` loads `.bot.local.env` first, then `.env` as a fallback.

## `gh_app_token.sh`

`scripts/gh_app_token.sh` mints a short-lived GitHub App installation token and uses it with the GitHub CLI (`gh`).

This is used so pull requests can be created by the GitHub App identity (for example, `Code Assist Bot`) instead of the repository owner's personal GitHub account.

### What it does

1. Loads GitHub App config from `.bot.local.env` first, then `.env` as a fallback.
2. Creates a signed JWT using the GitHub App private key (`.pem`).
3. Exchanges that JWT for a short-lived installation access token from GitHub.
4. Either:
   - prints shell exports (`GH_TOKEN`) for your current shell, or
   - runs `gh ...` directly with the token.

### Required local configuration

Create a repo-local `.bot.local.env` file (already ignored by `.gitignore`) with:

```env
GITHUB_APP_ID=...
GITHUB_APP_INSTALLATION_ID=...
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/app.private-key.pem
```

Notes:
- Do not commit `.bot.local.env`.
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
  --head feature/my-branch \
  --title "..." \
  --body "..."
```

### Why this exists (identity model)

There are three separate identities in the workflow:

- `git commit` author identity:
  - set with one-off flags (for example `Claude <claude@anthropic.com>`)
  - use the actual bot name for proper attribution
- `git push` auth:
  - usually your machine's SSH key
- `gh` API identity (PR creator):
  - GitHub App installation token (`GH_TOKEN`)

This script only affects the third one (`gh` API identity).

## `git_bot_commit.sh`

`scripts/git_bot_commit.sh` wraps `git commit` using one-off `user.name` / `user.email` flags so repository/global Git config is not modified.

It reads these values from `.bot.local.env` (or falls back to defaults):

```env
BOT_GIT_NAME=Claude  # Use actual bot name (Claude, Codex, etc.) for commit attribution
BOT_GIT_EMAIL=claude@anthropic.com
```

Examples:

```bash
git add README.md
scripts/git_bot_commit.sh -m "docs: update README"
```

```bash
scripts/git_bot_commit.sh --amend --no-edit
```

## Daily Workflow (Commit + PR as Bot)

This is the normal end-to-end workflow to make a change, commit it with bot identity (e.g., `Claude`), and create a pull request using the GitHub App identity.

1. Create a feature branch:

```bash
git checkout -b feature/my-change
```

2. Make your file changes and stage them:

```bash
git add <files>
```

3. Commit with bot identity (without changing Git config):

```bash
scripts/git_bot_commit.sh -m "feat: my change"
```

4. Push the branch (uses your normal SSH Git auth):

```bash
git push -u origin feature/my-change
```

5. Create the pull request as the GitHub App identity:

```bash
scripts/gh_app_token.sh --gh pr create \
  --base main \
  --head feature/my-change \
  --title "feat: my change" \
  --body "Describe the change."
```

### Security notes

- GitHub App installation tokens are short-lived.
- Protect the GitHub App private key (`.pem`); anyone with it can mint app tokens.
- Keep app permissions minimal and scoped to selected repositories.

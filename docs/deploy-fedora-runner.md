# Fedora Self-Hosted Deploy

This is the first CI/CD path for leetcoach.

Design:
- trigger deployment manually from GitHub Actions (`workflow_dispatch`)
- run tests first on GitHub-hosted Linux
- if tests pass, run deploy steps on your Fedora laptop through a self-hosted GitHub Actions runner
- no inbound ports or webhooks are required on Fedora; the runner only makes outbound connections to GitHub

## What This Workflow Does

Workflow file:
- [`.github/workflows/deploy-fedora.yml`](/Users/snayyer/repos/non-work/leetcoach/.github/workflows/deploy-fedora.yml)

Flow:
1. checkout selected ref
2. build Docker image on GitHub-hosted runner
3. run unit tests
4. run integration tests
5. hand off to Fedora self-hosted runner
6. copy stable `.env` from runner host into repo workspace
7. run `docker compose build`
8. run `docker compose run --rm bot migrate`
9. run `docker compose up -d bot scheduler`
10. run `doctor` checks and print recent logs

## One-Time Fedora Setup

### 1. Install Docker and Git

```bash
sudo dnf install -y git docker
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

### 2. Create a stable env location

The workflow expects your runtime env file here:

```bash
mkdir -p "$HOME/.config/leetcoach"
cp /path/to/your/leetcoach/.env "$HOME/.config/leetcoach/.env"
chmod 600 "$HOME/.config/leetcoach/.env"
```

### 3. Install a self-hosted GitHub runner

Go to:
- GitHub repo
- `Settings`
- `Actions`
- `Runners`
- `New self-hosted runner`

Choose:
- Linux
- x64

Then run the generated commands, typically in a dedicated directory:

```bash
mkdir -p "$HOME/actions-runner"
cd "$HOME/actions-runner"
```

GitHub will show commands similar to:

```bash
curl -o actions-runner-linux-x64.tar.gz -L <runner-download-url>
tar xzf actions-runner-linux-x64.tar.gz
./config.sh \
  --url https://github.com/nayyer28/leetcoach \
  --token <runner-registration-token> \
  --name fedora-leetcoach \
  --labels leetcoach-fedora \
  --unattended
```

Important:
- keep the custom label exactly `leetcoach-fedora`
- that label is what the deploy workflow targets

### 4. Install the runner as a service

```bash
cd "$HOME/actions-runner"
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

### 5. Verify runner readiness

In GitHub:
- `Settings`
- `Actions`
- `Runners`

You should see the Fedora runner online with label `leetcoach-fedora`.

## How To Trigger A Deploy

1. Push your branch and merge to `main`, or decide which ref you want to deploy.
2. In GitHub, open:
   - `Actions`
   - `Deploy Fedora`
3. Click `Run workflow`
4. Enter ref:
   - `main`
   - or a specific branch/tag/commit SHA if you want
5. Start the workflow

## What To Expect During Deployment

The Fedora runner will:
- checkout the chosen ref into the runner workspace
- copy `~/.config/leetcoach/.env` into that workspace
- rebuild the Docker image
- apply migrations
- restart `bot` and `scheduler`
- run `doctor` checks

The database stays intact because Docker Compose uses the named volume `leetcoach_data`.

## Troubleshooting

- runner job never starts
  - check that Fedora runner is online in GitHub settings
  - check that runner has label `leetcoach-fedora`

- deploy fails on `docker info`
  - runner user cannot access Docker
  - ensure the runner user is in the `docker` group
  - restart session/service after changing group membership

- deploy fails because `.env` is missing
  - create `~/.config/leetcoach/.env` on Fedora

- deploy fails on migration or doctor
  - inspect workflow logs
  - run the same commands manually on Fedora:

```bash
docker compose run --rm bot migrate
docker compose run --rm bot doctor
docker compose run --rm bot scheduler-doctor
docker compose logs --tail=100 bot
docker compose logs --tail=100 scheduler
```

## Future Upgrade Path

Once this manual flow feels safe, you can extend it to:
- deploy automatically on pushes to `main`
- require successful tests before deployment
- add rollback or health-based post-deploy checks

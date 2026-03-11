# leetcoach v3 Spec (Draft)

## Goal

Make leetcoach production-ready for low-cost always-on deployment with clear observability.

## Scope (v3)

- logging and monitoring baseline with Prometheus metrics
- deployment hardening and Kubernetes-ready packaging
- operational refinements for reliability and maintainability

## Track A: Logging and Monitoring

### A1. Structured logging

- switch runtime logs to JSON format
- include stable fields:
  - `service` (`bot` or `scheduler`)
  - `event`
  - `telegram_user_id` (when present)
  - `command` (when present)
  - `duration_ms` (for external calls)
  - `error_type` / `error_message`

### A2. Prometheus metrics

- expose `/metrics` endpoint from app process
- minimum counters/gauges:
  - `leetcoach_bot_commands_total{command=...}`
  - `leetcoach_reminders_sent_total`
  - `leetcoach_reminders_failed_total`
  - `leetcoach_scheduler_runs_total`
  - `leetcoach_scheduler_run_duration_seconds`
  - `leetcoach_gemini_requests_total{model=...,status=...}`
  - `leetcoach_gemini_fallback_total{from_model=...,to_model=...}`

### A3. Grafana dashboard

- bot traffic panel (commands/day)
- reminder delivery health panel (sent vs failed)
- scheduler behavior panel (runs, duration, selected count)
- Gemini panel (usage by model + fallback rate + failures)

## Track B: Kubernetes Formulation

Target: deploy cleanly on single-node `k3s` first, then scale to managed clusters.

### B1. K8s manifests/Helm chart

- Deployment for `bot`
- Deployment or CronJob/worker for `scheduler`
- ConfigMap + Secret wiring for env vars
- PVC for SQLite (single-node baseline)

### B2. Health and lifecycle

- readiness/liveness probes
- graceful shutdown handling
- startup preflight retained (`doctor`/`scheduler-doctor` parity)

### B3. Release workflow

- build/push tagged image
- deploy with version pinning
- rollback recipe

## Track C: Suggested Refinements

- split scheduler interval and daily dispatch windows for better control
- add dead-letter style retry policy for failed reminder sends
- add DB backup/restore CLI subcommands
- add optional Postgres backend path (future, if multi-user scale grows)

## Out of Scope (v3)

- full multi-tenant auth model
- rich web dashboard UI
- advanced quiz analytics/spaced scheduling policy redesign

## Acceptance Criteria (v3)

- JSON logs emitted consistently for bot and scheduler
- Prometheus endpoint exposed and scrapeable
- Grafana dashboard file(s) committed and usable
- local Docker run and k3s deployment both documented and working
- failure scenarios are diagnosable from logs + metrics without attaching debugger

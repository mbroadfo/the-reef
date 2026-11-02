# Reef 1.0 retirement record

Reef 1.0 (CrewAI committee, scanner, stop-loss monitor, daily report, MongoDB-backed Tank, live dashboard) was removed from the active repository. The last commit that contains it is `f6fdbe1` on `master`. Git history is the archive; there is no second copy of the old code in the tree.

**Not touched by this change:** MongoDB Atlas (the `the_reef` and `the_reef_dev` databases, including the Epoch 0 records), AWS resources, GitHub secrets and settings. All of it still exists exactly as before.

## Workflows (14 files before, 5 after)

State on GitHub when inventoried (2026-11-01). None of the retired ones had run recently: the trading workflows were already disabled manually.

| Workflow | State | Trigger | Paid LLM | Atlas | Deploys | Disposition |
|---|---|---|---|---|---|---|
| Scanner | disabled | cron 20 min + 9:30 | no | write | no | removed |
| Stop-Loss Monitor | disabled | cron 30 min | keys wired, CrewAI | write | no | removed |
| Daily Performance Report | disabled | cron 4:30pm ET | no | write | no | removed |
| Deep Dive | disabled | manual | Anthropic + OpenAI | write | no | removed |
| Tools: Reset Conviction | disabled | cron 9:30 ET | no | write | no | removed |
| Tools: Backfill Decisions | disabled | manual | no | write | no | removed |
| Tools: Seed 2025 History | disabled | manual | no | write | no | removed |
| Tools: DB Audit | active | manual | no | read | no | removed |
| Tools: Shark Audit | active | manual | no | read | no | removed |
| CI: Pull Request Checks | active | pull_request | no | no | no | **kept**; gains the `hygiene` job |
| Release Gate Test | active | manual | no | no | no (echo only) | kept |
| DevOps: Frontend | disabled | manual, gated | no | no | S3 + CloudFront | kept (see below) |
| DevOps: Backend | disabled | manual, gated | no | no | Lambda | kept (see below) |
| DevOps: Infrastructure | disabled | manual, gated | no | writes SSM param | Terraform apply | kept; hardcoded URI replaced by the `MONGODB_URI` secret |

No workflow has a schedule any more. The only automatic trigger is `ci.yml` on pull requests, which has no secrets, no AWS, no Atlas and no LLM access. Status check names `frontend`, `backend`, `terraform` and `tests` are unchanged, so the branch ruleset needs no edit; add `hygiene` as a required check when you want it enforced.

The `hygiene` job reproduces the useful part of draft PR #13: it fails a PR that adds an Atlas connection string, user or host to any tracked file. #13 itself is not merged and can be closed; its secret rename (`MONGODB_URI`) applies only to `devops-infrastructure.yml`, which is dispatch-only and fails safe (writes nothing) while the secret is empty.

## Python

| Removed | Why it was safe |
|---|---|
| `the_reef/main.py`, `crew.py`, `config/*.yaml`, `dashboard.py` | CLI and CrewAI wiring; nothing in `engine`, `ledger`, `risk`, `pods`, `backtest`, `aquarium`, `tests` imports them |
| `the_reef/brokerage/` (Tank, performance) | PyMongo paper broker; superseded by the ledger |
| `the_reef/scanner/`, `tools/` (CrewAI tools), `notifications/` | Reef 1.0 signal detection, agent tools, SMS |
| `tools/` scripts: `backfill_decisions`, `db_audit`, `reset_conviction_points`, `seed_history`, `shark_audit` | Atlas utilities for the 1.0 collections |
| `data/tank_state.json` | Stateful file from the local Tank |

Checked with an AST import scan of `the_reef`, `tools` and `tests`; the full suite then passes (301 tests) and `build_competition_snapshot.py` regenerates `snapshot.json` byte for byte.

Dependencies: `anthropic`, `crewai`, `crewai-tools`, `openai`, `pydantic`, `pymongo`, `requests`, `rich`, `schedule` removed from the runtime set; `yfinance` moved to an opt-in `data` group (used only by `tools/fetch_history.py`). `uv.lock` went from 3,865 to 685 lines (125 fewer packages locked (162 to 37)).

## Frontend

Removed the Reef 1.0 dashboard: its 6 pages, 20 components, context, API client, types and helpers, the screenshot scripts and 3 unused images, plus the `lucide-react` dependency and the root `package.json` that only served `screenshot.mjs`. The Aquarium, team pages, proposal stories and Research Lab are untouched apart from dropping the "Legacy dashboard" nav link. Unknown URLs, including the old `/dashboard` paths, redirect to `/`.

## Docs

Removed four Reef 1.0 narratives (committee spec, automation, runbook, architecture overview). Kept the Reef 2.0 notes, release management, and the infrastructure and security notes, which still describe the retained AWS stack.

## AWS and Atlas inventory (from Terraform and workflows; no live AWS or Atlas calls were made)

| Resource | Defined in | Used by |
|---|---|---|
| S3 bucket (static site), versioned, private | `dashboard/infra/s3.tf` | frontend deploy |
| CloudFront distribution + OAC + cache policy | `s3.tf` | `reef.broadfoot.consulting` |
| ACM certificate + validation | `s3.tf` | CloudFront TLS |
| Lambda `api`, IAM role, log group | `lambda.tf` | Reef 1.0 API only |
| API Gateway HTTP API, stage, route, permission | `api_gateway.tf` | Reef 1.0 API only |
| SSM SecureString `/reef/prod/secrets` | `lambda.tf` | holds the Atlas URI for the Lambda |
| S3 Terraform state `reef-tf-state` (us-west-2) | workflow backend config | Terraform |
| MongoDB Atlas `reef-m0`: `the_reef`, `the_reef_dev` | external | Reef 1.0 and Epoch 0 records; nothing in this repository reads it now |

Secrets referenced by workflows: `DEPLOY_AWS_*`, `TERRAFORM_AWS_*`, `TERRAFORM_PLAN_AWS_*`, `REEF_S3_BUCKET`, `MONGODB_URI` (and the old `MONGODB_PASSWORD`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SERPER_API_KEY`, `SMTP_*`, `SMS_RECIPIENT`, now referenced by nothing).

## Recommendations (separate decisions, none applied)

1. **Retain** the Terraform for S3, CloudFront and ACM, and `DevOps: Frontend` + `DevOps: Infrastructure`, if you want the aquarium publicly hosted. The snapshot is a static file, so the site needs no backend. Idle cost is pennies.
2. **Retire later, in its own PR:** `dashboard/backend/`, the Lambda, API Gateway and SSM resources in Terraform, `DevOps: Backend`, and the `backend` job's handler compile. Nothing in the aquarium calls the API. Review the Terraform plan (it will show destroys) before any apply, and update the ruleset's required `backend` check in the same step.
3. **Housekeeping needing your approval:** delete the unused secrets listed above; close #13; correct `MONGODB_URI` and run the ping-only auth check (still pending); decide whether to export the Epoch 0 collections before the Atlas M0 cluster is ever paused or removed.
4. Old workflow runs and the registered-but-absent "Atlas Ping Probe" and "Gate Probe" entries remain visible in the Actions tab; GitHub removes the latter once their runs age out.

## Standing constraints

$0 in new recurring costs; no paid LLM calls or services without Mike's separate authorization (the $2/day, $30/month LLM cap is a ceiling, not permission); no broker API, trading activation, Atlas access or unapproved deployment. `MONGODB_URI` is a legacy infrastructure dependency pending retirement and is not needed for Reef 2.0 development.

## Before and after

See the pull request description.

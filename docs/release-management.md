# Release management

Production changes (dashboard frontend, Lambda backend, Terraform) are deployed only by an explicit, approved, manual run. Merging to `master` deploys nothing.

## Rules

1. `master` accepts changes through pull requests only, after the required checks pass.
2. Deploy workflows (`DevOps: Frontend`, `DevOps: Backend`, `DevOps: Infrastructure`) have **no push trigger**. They run by `workflow_dispatch`, only from `master`.
3. Every deploying job uses the `production` environment, which requires a named reviewer's approval before the job starts.
4. Infrastructure: `plan` runs first (ungated) and prints the Terraform plan plus its SHA-256. `infra` waits for approval, builds the same deterministic Lambda zip, re-plans, **fails if the new plan's hash differs from the reviewed one**, and applies that saved plan file. There is no `-auto-approve` of a fresh plan. A plan file is not handed between jobs because artifacts on a public repository are readable by any signed-in GitHub user; the hash is the handoff. If provider or dependency versions drift between the two runs the job fails safe and you re-run.
5. AWS credentials are set on the steps that call AWS, not on whole jobs, so `pip`, `npm` and third-party actions never see them. The plan job uses `TERRAFORM_PLAN_AWS_*` when those secrets exist (create a read-only IAM user for it) and otherwise falls back to `TERRAFORM_AWS_*`.
6. Trading and LLM workflows are `workflow_dispatch` only until a separate activation decision. Provider keys live only in a gated `llm` environment.

## Repository settings (not stored in the repo; applied 2026-10-30, listed here so they can be re-created)

Settings are not part of any diff. They were applied through the GitHub API as described below; re-apply them if the repository is recreated.

```bash
# 1. Environment with a required reviewer (replace USER_ID with the numeric GitHub user id of the reviewer)
gh api -X PUT repos/{owner}/{repo}/environments/production \
  -f 'reviewers[][type]=User' -F 'reviewers[][id]=USER_ID' \
  -F 'deployment_branch_policy[protected_branches]=false' \
  -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api -X POST repos/{owner}/{repo}/environments/production/deployment-branch-policies -f name=master

# 2. Branch ruleset: PR required, status checks required, no force-push or deletion
#    Required checks (job names from .github/workflows/ci.yml): frontend, backend, terraform
```

Branch ruleset (Settings > Rules > Rulesets), target `master`:
- Restrict deletions; block force pushes.
- Require a pull request before merging. Approvals: 0, because there is one maintainer. Do not enable mandatory second-person review.
- Repository admins can bypass on pull requests only (escape hatch); direct pushes stay blocked.
- Require status checks to pass: `frontend`, `backend`, `terraform`. These names exist only after `ci.yml` has run once on a PR.

Environment secrets and variables for `production` (move them out of repository scope when convenient): `DEPLOY_AWS_*`, `TERRAFORM_AWS_*`, `REEF_S3_BUCKET`, `MONGODB_URI` (production Atlas connection string, used to write the Lambda's SSM parameter).

## Testing the gates (required before any deploy workflow is re-enabled)

1. Run **Release Gate Test** from `master`: expect the job to wait for approval, then pass and print "nothing was deployed".
2. Run **Release Gate Test** from a non-master branch: expect the job to be skipped.
3. Open a PR that breaks typecheck: expect `frontend` to fail and merging to be blocked.
4. Open a PR that touches `dashboard/frontend/**`: expect **no** deployment to start after merge.
5. Run **DevOps: Infrastructure** and read the `plan` log; reject the `apply` approval and confirm nothing changed.
6. Only then `gh workflow enable` the three DevOps workflows, and keep them manual.

## Rollback

Deploy workflows rebuild from `master`; roll back by reverting on `master` through a PR and dispatching the deploy again.

## Database connection details

No Atlas host, user name, or connection string is stored in the repository. Workflows read `secrets.MONGODB_URI` from their environment: the `dev` environment for tool and (disabled) trading workflows, the `production` environment for the Lambda's SSM parameter. The `CI: Repository Hygiene` check fails any PR that adds a connection string or Atlas host to tracked files. Database names are passed separately (`MONGODB_DB`, workflow inputs).

Earlier commits still contain the old host and user name (a public history cannot be rewritten safely). They are identifiers, not credentials; the password was always a secret.

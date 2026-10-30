# Release management

Production changes (dashboard frontend, Lambda backend, Terraform) are deployed only by an explicit, approved, manual run. Merging to `master` deploys nothing.

## Rules

1. `master` accepts changes through pull requests only, after the required checks pass.
2. Deploy workflows (`DevOps: Frontend`, `DevOps: Backend`, `DevOps: Infrastructure`) have **no push trigger**. They run by `workflow_dispatch`, only from `master`.
3. Every deploying job uses the `production` environment, which requires a named reviewer's approval before the job starts.
4. Infrastructure: `plan` runs first and prints the Terraform plan; `apply` and the SSM secrets step wait for approval. Read the plan in the `plan` job's log before approving. A plan file is intentionally not passed between jobs, because artifacts on a public repository are readable by any signed-in GitHub user.
5. Trading and LLM workflows are `workflow_dispatch` only until a separate activation decision. Provider keys live only in a gated `llm` environment.

## One-time repository settings (apply after this change is reviewed and merged)

Settings are not stored in the repository, so a reviewer cannot see them in the diff. Apply them in this order and tick each off.

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
- Require a pull request before merging (approvals: 0 for a solo maintainer, but keep the PR requirement).
- Require status checks to pass: `frontend`, `backend`, `terraform`. These names exist only after `ci.yml` has run once on a PR.
- Do not add a bypass actor unless intended.

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

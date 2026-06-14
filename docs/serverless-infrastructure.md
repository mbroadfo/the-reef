# The Reef — Serverless Infrastructure

## Design Philosophy

The infrastructure is built to cost nothing when idle and scale automatically under load. There are no EC2 instances, no containers, no managed services with per-hour billing. Every component either runs on a consumption model or uses a permanently free tier.

---

## AWS Stack

```
Internet
    │
    ▼
CloudFront (E1HWKA7ET1TL2K)
    ├── /api/* → API Gateway → Lambda
    └── /*     → S3 (reef-dashboard-broadfoot)
```

### CloudFront

- Single distribution serves both the React SPA and API proxy
- TLS terminated at the edge using ACM certificate (us-east-1, `83988c89...`)
- Custom domain: `reef.broadfoot.consulting` via Cloudflare DNS (CNAME, unproxied)
- Fallback origin: `d2426mi6b1xoun.cloudfront.net`
- SPA routing: 403/404 responses rewritten to `/index.html`

### API Gateway

- REST API: `https://o1su046k2i.execute-api.us-west-2.amazonaws.com/`
- Stage: `prod`
- All routes proxy to the `reef-dashboard` Lambda function
- No authentication layer — dashboard is read-only public data

### Lambda

- Function: `reef-dashboard`
- Runtime: Python 3.12
- Handler: `handler.lambda_handler`
- Deployment: zip artifact built in CI, uploaded via AWS CLI
- Cold start: ~300ms (acceptable for dashboard polling intervals)
- Timeout: 30s (sufficient for MongoDB queries + yfinance sector fetch)

### S3

- Bucket: `reef-dashboard-broadfoot`
- Purpose: static frontend assets (JS, CSS, fonts, images)
- Access: CloudFront only (bucket policy restricts direct access)
- Terraform state: `s3://reef-tf-state/reef-dashboard/terraform.tfstate`

### ACM Certificate

- ARN: `arn:aws:acm:us-east-1:...:certificate/83988c89-3d4d-4311-ab85-a8da73cc6022`
- Status: Issued
- Region: us-east-1 (required for CloudFront)
- Validation: DNS via Cloudflare

---

## MongoDB Atlas

- Cluster: `reef-m0` (free M0 shared cluster)
- Databases: `the_reef` (prod), `the_reef_dev` (dev)
- Connection: via `MONGODB_URI` GitHub Secret — never in code or files
- No VPC peering — Atlas IP allowlist + TLS-only connection

### Collections

| Collection | Purpose |
|---|---|
| `portfolio` | Cash balance, starting_cash, display metadata |
| `portfolio_snapshots` | Daily NAV snapshots (260+ records), drives chart |
| `positions` | Open positions (ticker, shares, avg_cost, stop_loss) |
| `trades` | Full trade history (BUY/SELL, pnl, surfaced_by, signal_type) |
| `signals` | Scanner output — raw signals before deep dive |
| `decisions` | Apex rationale records for each trade decision |

---

## Terraform

Infrastructure is defined as code in `dashboard/infra/`. State is stored remotely.

```
dashboard/infra/
├── main.tf          — provider, S3 backend config
├── lambda.tf        — function, IAM role, execution policy
├── api_gateway.tf   — REST API, stage, resource/method tree
├── cloudfront.tf    — distribution, origins, behaviors, OAC
├── s3.tf            — frontend bucket, policy
├── acm.tf           — certificate (us-east-1 provider alias)
├── variables.tf     — region, bucket name, domain
└── outputs.tf       — distribution ID, API URL
```

Partial backend config: bucket/key/region passed explicitly in CI to avoid committing state coordinates to source.

### Apply trigger

`devops-infrastructure.yml` runs on push to `dashboard/infra/**`. Terraform plan is shown in the Actions log; apply runs automatically. No manual `terraform apply` needed for routine changes.

---

## IAM — github-actions-ci User

A dedicated IAM user with the minimum permissions needed for CI/CD. No console access, no human login.

### Allowed Actions

| Service | Permissions |
|---|---|
| S3 | PutObject, GetObject, DeleteObject, ListBucket (frontend bucket + state bucket) |
| CloudFront | CreateInvalidation (distribution E1HWKA7ET1TL2K only) |
| Lambda | GetFunction, UpdateFunctionCode, PublishVersion |
| SSM | GetParameter (for any `/reef/*` parameters) |

### Denied by Absence

- No EC2, RDS, EKS, or other service access
- No IAM modifications
- No access to other S3 buckets
- No CloudFront distribution management (only invalidation)

Credentials stored as `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` GitHub Secrets.

---

## DNS

Cloudflare manages the `broadfoot.consulting` zone.

| Record | Type | Value | Proxy |
|---|---|---|---|
| `reef` | CNAME | `d2426mi6b1xoun.cloudfront.net` | DNS only (unproxied) |

Unproxied because CloudFront handles TLS and CDN — double-proxying via Cloudflare would break certificate validation and add latency.

---

## Cost Breakdown

| Service | Tier | Monthly Cost |
|---|---|---|
| MongoDB Atlas M0 | Free forever | $0 |
| AWS Lambda | Free tier (1M req/month) | $0 |
| API Gateway | Free tier (1M req/month) | $0 |
| CloudFront | Free tier (1TB transfer/month) | ~$0 |
| S3 (frontend + state) | <1GB storage | <$0.03 |
| ACM Certificate | Free | $0 |
| Cloudflare DNS | Free plan | $0 |
| GitHub Actions | Free (public/private minutes) | $0 |
| **Infrastructure total** | | **<$1/month** |

Variable cost is LLM inference. At 2–3 deep dives per trading day:

| Model | Avg cost/dive | Daily (2 dives) | Monthly |
|---|---|---|---|
| GPT-4o-mini (Hunter) | ~$0.01 | $0.02 | ~$0.40 |
| GPT-4o (Research/Macro/Sentiment/Wildcard) | ~$0.08 | $0.32 | ~$6.40 |
| Claude Sonnet 4.6 (Contrarian/Risk/Apex) | ~$0.06 | $0.24 | ~$4.80 |
| **Total LLM** | | **~$0.58/day** | **~$12/month** |

**Total system cost: ~$13/month** at moderate activity.

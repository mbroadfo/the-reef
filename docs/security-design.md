# The Reef — Security Design

## Security Posture

The Reef handles financial logic and API credentials. The design applies a small number of hard rules consistently rather than relying on layered controls that can drift. The result is a system where the attack surface is narrow, the blast radius of any compromise is bounded, and there are no secrets anywhere that could be accidentally committed or exposed.

---

## Secrets Management

### Rule: No secrets in code, files, or git — ever

All credentials are stored as GitHub Secrets and injected as environment variables at workflow runtime. This is a hard constraint in `CLAUDE.md` — not a preference.

| Secret | Used By |
|---|---|
| `MONGODB_URI` | All trading workflows + Lambda backend |
| `OPENAI_API_KEY` | CrewAI (GPT-4o, GPT-4o-mini agents) |
| `ANTHROPIC_API_KEY` | CrewAI (Claude Sonnet 4.6 agents) |
| `SERPER_API_KEY` | Web search tool (SerperDevTool) |
| `AWS_ACCESS_KEY_ID` | Deploy workflows (S3, CloudFront, Lambda) |
| `AWS_SECRET_ACCESS_KEY` | Deploy workflows |
| `REEF_S3_BUCKET` | Terraform backend bucket name |

No `.env` files exist in the repository. No secrets are passed via command-line arguments (visible in process lists). No secrets appear in workflow logs.

---

## No Broker API

The system has no connection to any live brokerage. `ExecuteBuyTool` and `ExecuteSellTool` write to MongoDB — they do not call eTrade, Alpaca, Tradier, or any other broker API.

This is a deliberate architectural constraint:
- Eliminates the highest-value credential (a live brokerage token)
- Eliminates the risk of runaway AI trades affecting real money
- Forces manual review of every paper trade before real execution

The constraint will remain until the system demonstrates consistent edge over a meaningful sample size.

---

## IAM Least Privilege

The CI/CD IAM user (`github-actions-ci`) has exactly the permissions needed for deployment and nothing else.

**What it CAN do:**
- Upload/list/delete objects in the frontend S3 bucket
- Read/write the Terraform state S3 bucket
- Create CloudFront cache invalidations (this distribution only)
- Update Lambda function code and publish versions
- Read SSM parameters under `/reef/*`

**What it CANNOT do:**
- Modify IAM roles or policies
- Access any other S3 bucket
- Read EC2, RDS, or any other service
- Delete the Lambda function or CloudFront distribution
- Access the MongoDB Atlas control plane

If these credentials were compromised, an attacker could update the Lambda code and frontend assets — but could not access the database credentials (GitHub Secrets are not readable via AWS APIs), could not pivot to other AWS resources, and could not affect real money.

---

## Transport Security

All data in transit is encrypted:

| Path | Mechanism |
|---|---|
| Browser → CloudFront | TLS 1.2+ via ACM certificate |
| CloudFront → S3 | HTTPS (OAC — Origin Access Control) |
| CloudFront → API Gateway | HTTPS |
| API Gateway → Lambda | Internal AWS (encrypted) |
| Lambda → MongoDB Atlas | TLS (MongoDB driver, `tls=true` enforced by Atlas M0) |
| GitHub Actions → AWS | HTTPS via AWS CLI |
| GitHub Actions → MongoDB | TLS via `MONGODB_URI` (Atlas connection string) |

No unencrypted traffic paths exist in the system.

---

## MongoDB Atlas Access Control

- **TLS only** — Atlas M0 does not support non-TLS connections
- **IP allowlist** — configured to allow GitHub Actions runner IPs and Lambda (via NAT or 0.0.0.0/0 on M0 free tier, which is a known M0 limitation)
- **Database user** — single user with read/write access to `the_reef` and `the_reef_dev` only
- **No Atlas admin access** from application code — the `MONGODB_URI` connects as a database user, not an org admin

---

## No Stateful Data to Files or Git

All runtime state lives in MongoDB. The following are explicitly prohibited:
- Writing portfolio state, trade history, or signals to JSON/CSV files
- Committing any runtime data to git
- Using SQLite or any local file-based database
- Caching API responses to disk

This prevents accidental exposure of trading data in git history and ensures a single source of truth.

---

## Frontend Security

The React dashboard is a static SPA with no server-side rendering and no user authentication layer. Security considerations:

- **Read-only public data** — the dashboard displays paper trading performance; no PII, no real financial data
- **No user input to backend** — all API routes are GET; no POST/PUT/DELETE from the frontend
- **No API keys in frontend code** — the Lambda backend holds all third-party credentials; the frontend only calls `/api/*`
- **Content Security Policy** — not yet implemented (low priority for a read-only public dashboard)
- **CORS** — API Gateway allows the CloudFront domain only

---

## Dependency Supply Chain

- Python dependencies managed via `uv` with a lockfile (`uv.lock`)
- Node dependencies managed via npm with a lockfile (`package-lock.json`)
- Both lockfiles are committed to git
- Dependabot or automated scanning: not yet configured (future)

---

## Incident Blast Radius

| Scenario | Impact | Mitigation |
|---|---|---|
| GitHub Secrets leaked | Attacker can call LLM APIs and update Lambda/S3 | Rotate secrets; no real money exposed |
| MongoDB URI leaked | Attacker can read/write paper trade data | Rotate credentials in Atlas; no real money |
| Lambda code replaced | Dashboard shows attacker-controlled data | Detect via CloudFront logs; redeploy from git |
| AWS keys leaked | Attacker can update Lambda + frontend | Rotate via IAM; scoped permissions limit blast radius |
| LLM keys leaked | API cost abuse | Rotate; set spend limits in provider console |

In all scenarios: **no real money is at risk**. The broker firewall (no API) is the most important security control in the system.

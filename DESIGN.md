# NimbusKart — Design Document

## 1. Multi-Cloud Architecture

The core architecture decouples resource provisioning (Terraform) from cost detection (Python) via a shared data model — the janitor's findings schema. This allows the cost-hygiene pipeline to span clouds without per-cloud orchestration logic.

```
┌────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                      │
│  GitHub Actions / Jenkins / Argo Workflows                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Terraform (provision) → Janitor (scan) → Report    │    │
│  └────────────────────────────────────────────────────┘    │
├────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │   AWS      │  │   GCP      │  │   Azure    │           │
│  │ LocalStack │  │ Cloud SDK  │  │ Azure CLI  │           │
│  └────────────┘  └────────────┘  └────────────┘           │
└────────────────────────────────────────────────────────────┘
```

Each cloud provider has an adapter in the janitor that normalizes findings into the common schema.

## 2. Adding GCP / Azure

### GCP
- Add `gcp_janitor.py` with a `scan()` function that calls the Compute API, Cloud Storage API, and Cloud Asset Inventory.
- Use `google-cloud-sdk` and `google-auth` libraries.
- The `Protected=true` label convention maps to GCP labels.
- Pricing constants live in `constants.py` alongside AWS values.

### Azure
- Add `azure_janitor.py` using the Azure SDK for Python (`azure-mgmt-compute`, `azure-mgmt-storage`).
- Resource graph queries replace paginated describe calls.
- The `Protected=true` tag maps to Azure resource tags.

Both adapters write to the same `report.json` schema so downstream tooling (Slack webhooks, Jira tickets, PowerBI dashboards) is cloud-agnostic.

## 3. Module Boundaries

```
terraform/
├── main.tf              — Root orchestrator
├── modules/
│   ├── network/          — VPC, subnets, IGW, RT
│   ├── compute/          — EC2 + ASG (future)
│   ├── storage/          — S3 + lifecycle (future)
│   └── security/         — SG, NACL, KMS (future)

janitor/
├── janitor.py            — Entry point, arg parsing, report generation
├── constants.py          — Pricing data, thresholds, region
├── detectors/
│   ├── ebs.py            — Unattached volume detection
│   ├── ec2.py            — Stopped instance detection
│   ├── eip.py            — Elastic IP detection
│   └── tags.py           — Missing-tag detection
```

Current implementation is flat for simplicity; each detector function is a clear refactoring target into its own module.

## 4. IAM Policies

Since LocalStack does not enforce IAM, `provider.tf` uses static fake credentials. In real AWS the janitor would need:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVolumes",
        "ec2:DescribeInstances",
        "ec2:DescribeAddresses",
        "s3:ListAllMyBuckets",
        "s3:GetBucketTagging",
        "ec2:DeleteVolume",
        "ec2:ReleaseAddress"
      ],
      "Resource": "*"
    }
  ]
}
```

**Principle of least privilege**: the janitor role has `Describe` for scanning and specific `Delete`/`Release` for cleanup. It does not have `ec2:TerminateInstances` or `s3:DeleteBucket`.

## 5. Safe Delete Guardrails

| Guardrail | Implementation |
|---|---|
| Default dry-run | `--dry-run` is the default; explicit `--delete` required |
| Protected tag | Resources with `Protected=true` are skipped in delete mode |
| Age threshold | Stopped instances < 14 days old are not reported as orphans |
| Human-in-the-loop | Reports must be reviewed before production delete runs |
| Audit trail | Every delete action is logged with resource ID and timestamp |

### Future guardrails
- **Quarantine**: Move resources to a "to-be-deleted" state for 7 days before permanent removal.
- **Dependency check**: Before deleting a volume, verify it's not referenced in a snapshot or AMI.
- **Approval webhook**: Require a Slack approval before delete proceeds.

## 6. Outage Prevention

| Risk | Mitigation |
|---|---|
| Janitor deletes in-use volume | `Attachments` check before reporting; `Protected` tag |
| Terraform destroys prod infra | `terraform apply` only targets staging workspace |
| CI pipeline fails on orphan | Dry-run exits 1; PR comment provides context, does not block merge |
| LocalStack state loss | Scripts idempotent; `terraform apply` re-creates missing resources |

## 7. Observability Metrics

| Metric | Source | What it tells |
|---|---|---|
| `total_orphans` | report.json | Cost hygiene trend over time |
| `estimated_monthly_waste_usd` | report.json | Dollar impact of inaction |
| `orphan_{type}_count` | report.json | Which resource type degrades fastest |
| `protected_tag_hit_rate` | report.json | How widely the protection pattern is used |
| Pipeline duration | GitHub Actions | Regression in scan speed |

### Logging

Structured JSON logs emitted to stdout:
```json
{"timestamp": "...", "level": "INFO", "resource": "vol-abc", "action": "deleted", "duration_ms": 120}
```

## 8. Alerts

| Condition | Channel | Severity |
|---|---|---|
| New orphan detected > $10/mo | Slack #cost-alerts | Warning |
| Same resource orphaned for > 2 scans | PagerDuty | Critical |
| Janitor fails to start | GitHub Actions notification | High |
| Delete mode removes protected resource | Security Slack channel | Critical |

Integration plan: GitHub Actions sends webhook to a lightweight alert router (e.g., `ntfy.sh` or `sparkpost`) → Slack / PagerDuty.

## 9. What Was Intentionally Not Built

- **Real-time streaming**: The janitor is batch-oriented. A real-time variant using EventBridge + Lambda would detect orphans within minutes.
- **Multi-account support**: The janitor scans a single account. Cross-account assume-role is not implemented.
- **Cost anomalies**: The janitor identifies waste (unused resources) but not anomalies (unexpected spikes). That requires a different tool (CloudHealth, Vantage).
- **Right-sizing recommendations**: Identifying oversized instances is a separate problem best handled by Compute Optimizer.
- **Budget enforcement**: No mechanism to enforce a monthly spending cap — this would require a separate budget controller that can scale down resources.
- **UI / Dashboard**: Reports are files only. A web dashboard (Grafana / Streamlit) is a natural next step.
- **Scheduled execution**: There is no cron/scheduler — the janitor runs only on PRs or manual invocation.
- **Remediation rollback**: Deleted resources cannot be restored (unless snapshot exists). We intentionally omitted a "recycle bin" pattern for simplicity.

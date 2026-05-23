# NimbusKart Cost Hygiene — Submission

## Project Summary

A fully-local, production-quality DevOps engineering project that:

1. **Provisions** a staging environment on LocalStack using reusable Terraform modules.
2. **Scans** for orphaned cloud resources (unattached EBS, stopped EC2, unassociated EIPs, missing tags).
3. **Reports** waste with estimated monthly costs in JSON and Markdown.
4. **Automates** the full pipeline via GitHub Actions on every pull request.

## What Was Implemented

| Requirement | Status |
|---|---|
| Terraform VPC, subnets, IGW, route tables | Done |
| Security group (HTTP 80/443, SSH from variable) | Done |
| 2 × EC2 t3.micro instances (web tier) | Done |
| S3 bucket with versioning + 30-day lifecycle | Done |
| Unattached EBS volume (orphan detection) | Done |
| Reusable Terraform module (network) | Done |
| Required tags on all resources | Done |
| Terraform variables, outputs, tfvars | Done |
| LocalStack provider configuration | Done |
| Python 3.11 cost janitor with argparse | Done |
| 4 scan types (EBS, EC2, EIP, tags) | Done |
| Dry-run mode (default) + delete mode | Done |
| Protected=true tag skip in delete | Done |
| JSON report (exact schema) | Done |
| Markdown report | Done |
| Static pricing in constants.py | Done |
| Structured logging (stdout) | Done |
| Non-zero exit on dry-run orphans | Done |
| pytest tests (18 test cases) | Done |
| GitHub Actions workflow | Done |
| DESIGN.md (multi-cloud, guardrails, alerts) | Done |
| Makefile, pre-commit, .gitignore, pyproject.toml | Done |
| Sample reports (JSON + Markdown) | Done |

## Self-Assessment

**Strengths**: The project is self-contained, requires no real AWS account, and demonstrates a clear separation of concerns between provisioning (Terraform) and cost analysis (Python). The CI pipeline is realistic and includes PR feedback. The design document addresses real-world concerns (IAM least privilege, safe deletion guardrails, outage prevention).

**Limitations**: Flat detector functions (not modularized into separate files); no GCP/Azure adapters (out of scope but designed for); batch-oriented instead of real-time; static pricing does not reflect regional differences.

## How to Evaluate

See `docs/walkthrough.md` for step-by-step instructions. The fastest path to verification:

```bash
docker run --rm -d --name localstack -p 4566:4566 \
  -e SERVICES=ec2,s3,sts,iam -e AWS_DEFAULT_REGION=us-east-1 \
  localstack/localstack:4.0.0
pip install -r janitor/requirements.txt terraform-local
cd terraform && tflocal init && tflocal apply -auto-approve
cd .. && python janitor/janitor.py --dry-run
```

## Repo Structure

```
├── README.md
├── SUBMISSION.md
├── DESIGN.md
├── terraform/
│   ├── main.tf, provider.tf, variables.tf, outputs.tf, terraform.tfvars
│   └── modules/network/
│       ├── main.tf, variables.tf, outputs.tf
├── janitor/
│   ├── janitor.py, constants.py, requirements.txt
│   ├── tests/test_janitor.py
├── .github/workflows/cost-janitor.yml
├── docs/walkthrough.md
├── samples/report.{example.json,example.md}
├── Makefile, .gitignore, pyproject.toml
```

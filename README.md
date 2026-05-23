# NimbusKart — Multi-Cloud Cost Hygiene & Automation

A fully-local DevOps infrastructure project that provisions a staging environment on [LocalStack](https://localstack.cloud/) (mock AWS) using Terraform, then scans it for orphaned and untagged resources with a Python-based cost janitor.

---

## Overview

NimbusKart demonstrates a real-world cost-hygiene pipeline:

- **Terraform** provisions a VPC, subnets, EC2 instances, an S3 bucket, and an intentionally unattached EBS volume.
- **Cost Janitor** (`janitor/janitor.py`) scans for unattached EBS volumes, long-stopped EC2 instances, unassociated Elastic IPs, and resources missing required tags.
- **GitHub Actions** orchestrates the full flow on every PR: starts LocalStack, runs Terraform, executes the janitor, uploads reports, and comments if orphans are found.
- **Everything runs locally** — no real AWS account, no paid services.

---

## How to run locally

### Prerequisites

- Docker Desktop
- Python 3.11+
- Terraform CLI >= 1.5
- `pip`

### 1. Start LocalStack

```bash
docker run --rm -d \
  --name localstack \
  -p 4566:4566 \
  -e SERVICES=ec2,s3,sts,iam \
  -e AWS_DEFAULT_REGION=us-east-1 \
  localstack/localstack:latest
```

### 2. Install dependencies

```bash
pip install -r janitor/requirements.txt
pip install terraform-local
```

### 3. Provision infrastructure

```bash
cd terraform
tflocal init
tflocal apply -auto-approve
```

### 4. Run the cost janitor

```bash
python janitor/janitor.py --dry-run
```

To delete orphaned resources:

```bash
python janitor/janitor.py --delete
```

### 5. Run unit tests

```bash
cd janitor
python -m pytest tests/ -v
```

### 6. Tear down

```bash
cd terraform
tflocal destroy -auto-approve
docker stop localstack
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    GitHub Actions                    │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │LocalStack │  │Terraform │  │  Cost Janitor     │  │
│  │ Container │→│  Apply   │→│  (dry-run)         │  │
│  └──────────┘  └──────────┘  └────────┬──────────┘  │
│                                       │              │
│                          ┌────────────▼──────────┐   │
│                          │   Upload reports &    │   │
│                          │   PR comment if waste  │   │
│                          └───────────────────────┘   │
└─────────────────────────────────────────────────────┘

                LocalStack (localhost:4566)
┌──────────────────────────────────────────────────────┐
│  Terraform Resources                                  │
│  ┌────────────────────┐   ┌──────────────────────┐   │
│  │ VPC 10.20.0.0/16  │   │  Security Group      │   │
│  │ ├─ subnet 1 (AZ a) │   │  ├─ 80 (HTTP)        │   │
│  │ ├─ subnet 2 (AZ b) │   │  ├─ 443 (HTTPS)      │   │
│  │ ├─ Internet GW     │   │  └─ 22 (SSH)         │   │
│  │ └─ Route Table     │   └──────────────────────┘   │
│  └────────────────────┘                              │
│  ┌────────────────────┐   ┌──────────────────────┐   │
│  │ EC2 × 2 (t3.micro) │   │ S3 bucket (versioned)│   │
│  │ tagged "web"       │   │ lifecycle: 30-day     │   │
│  └────────────────────┘   │ noncurrent expire     │   │
│                            └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐ │
│  │ EBS volume (10 GB, gp3) — intentionally         │ │
│  │ unattached for orphan detection                  │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### Janitor scan targets

| Resource | Detection rule |
|---|---|
| EBS volume | Not attached to any instance |
| EC2 instance | `stopped` state > N days (default 14) |
| Elastic IP | No `InstanceId` or `NetworkInterfaceId` association |
| Any resource | Missing `Project`, `Environment`, or `Owner` tag |

---

## Decisions & deviations

### Why SSH open to the world (0.0.0.0/0) is unsafe

The terraform.tfvars sets `ssh_cidr_blocks = ["0.0.0.0/0"]` by default. In a real environment this exposes SSH to the entire internet, inviting brute-force and exploitation. We document this but keep it as the default for two reasons: (1) this is a LocalStack demo where no actual network traffic flows, and (2) it forces the reader to consciously change the variable for production. **Always restrict SSH to a specific CIDR (e.g., your office VPN) in production.**

### Why public subnets are not production-safe

Placing instances directly in public subnets with public IPs bypasses load balancers, NAT gateways, and bastion hosts. In production, web tiers should sit in private subnets behind an Application Load Balancer in public subnets. This architecture is simplified intentionally to keep the assignment local and infrastructure-free.

### Key assumptions

- LocalStack mocks AWS but does not enforce IAM policies, network ACLs, or real pricing. All costs are calculated from static constants in `constants.py`.
- AMI IDs are fake — LocalStack accepts any valid-looking AMI ID.
- The `terraform-local` (`tflocal`) CLI wrapper transparently injects LocalStack endpoints into Terraform.

### Security tradeoffs

| Tradeoff | Rationale |
|---|---|
| No IAM roles | LocalStack does not enforce real IAM; static fake keys used |
| SSH open by default | Demo requirement; documented as insecure |
| Public subnets | Simplified topology; no NAT gateway or ALB |
| No encryption | LocalStack S3 does not enforce KMS; omitted for brevity |
| Single SG for all tier | Intentional simplification; prod would split web/app/db SGs |

### How LocalStack differs from real AWS

| Area | LocalStack | Real AWS |
|---|---|---|
| IAM | No real enforcement | Full policy evaluation |
| Instance types | Accepts any type string | Validates against real SKUs |
| Pricing | Free | Real billing applies |
| Tag propagation | Mostly instant | Can have propagation delays |
| Availability zones | Logical names only | Physical AZs with independent failure domains |

---

## Trade-offs

1. **Monolithic janitor vs. microservices** — A single Python script is simpler to debug, test, and deploy than a fleet of Lambda functions for a demo. For production at scale, split detectors by resource type into separate Lambda functions or Step Functions.

2. **LocalStack vs. moto** — LocalStack provides a real running service with consistent API behavior. `moto` is faster for unit tests but diverges from real AWS in edge cases. We test with `unittest.mock` for unit tests and LocalStack for integration.

3. **tflocal vs. manual endpoint config** — The `terraform-local` pip package is a thin wrapper. In CI we could set `AWS_ENDPOINT_URL` but `tflocal` is the standard approach used in the LocalStack ecosystem.

4. **Static pricing** — Real AWS pricing changes by region, volume type, and reservation model. Static constants are deliberately inexact — the janitor highlights waste trends, not precise billing.

---

## AI usage disclosure

This project was generated with the assistance of AI (Claude) as a productivity aid for boilerplate generation, file scaffolding, and documentation drafting. Every architectural decision, configuration value, and security tradeoff was reviewed and validated by a human engineer before inclusion. Specific areas where AI contributed:

- Initial file structure and Makefile scaffolding
- Terraform module skeleton generation
- Python test boilerplate
- Markdown documentation templates
- README wording suggestions

All logic, pricing constants, test assertions, and production-readiness decisions were made by the human author.

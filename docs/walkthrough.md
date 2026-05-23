# Walkthrough

## Prerequisites

- Docker Desktop (for LocalStack)
- Python 3.11+
- Terraform CLI (>= 1.5)
- pip

## 1. Start LocalStack

```bash
docker run --rm -d \
  --name localstack \
  -p 4566:4566 \
  -e SERVICES=ec2,s3,sts,iam \
  -e AWS_DEFAULT_REGION=us-east-1 \
  localstack/localstack:latest
```

Verify health:

```bash
curl -s http://localhost:4566/_localstack/health | jq .
```

## 2. Install Python dependencies

```bash
pip install -r janitor/requirements.txt
pip install terraform-local
```

## 3. Terraform

```bash
# Initialize
cd terraform
tflocal init

# Preview
tflocal plan

# Apply
tflocal apply -auto-approve

# Verify resources via LocalStack
aws --endpoint-url=http://localhost:4566 ec2 describe-instances
aws --endpoint-url=http://localhost:4566 s3api list-buckets
```

## 4. Run Cost Janitor

```bash
python janitor/janitor.py --dry-run --output-dir reports
```

Expected output:

```
2026-05-21T12:00:00 [INFO] janitor: NimbusKart Cost Janitor starting (dry-run=True)
2026-05-21T12:00:00 [INFO] janitor: Unattached volume: vol-... (10 GB, $0.80/mo)
2026-05-21T12:00:00 [INFO] janitor: Found 1 orphan(s), estimated monthly waste $0.80
2026-05-21T12:00:00 [WARNING] janitor: Orphans exist in dry-run mode -> exit code 1
```

View reports:

```bash
cat reports/report.json | jq .
cat reports/report.md
```

## 5. Delete mode (dry-run is default)

```bash
python janitor/janitor.py --delete --output-dir reports
```

Resources tagged `Protected=true` will be skipped.

## 6. Unit tests

```bash
cd janitor
python -m pytest tests/ -v
```

## 7. Cleanup

```bash
cd terraform
tflocal destroy -auto-approve
docker stop localstack
```

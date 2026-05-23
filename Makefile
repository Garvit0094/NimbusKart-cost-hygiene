.PHONY: help localstack localstack-stop setup init plan apply destroy fmt validate test lint clean dev

help:
	@echo "NimbusKart Cost Hygiene Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  localstack  Start LocalStack Docker container (v4.0.0)"
	@echo "  localstack-stop  Stop LocalStack container"
	@echo "  setup       Install Python dependencies (pip install -r requirements.txt)"
	@echo "  init        terraform init via tflocal"
	@echo "  plan        terraform plan via tflocal"
	@echo "  apply       terraform apply via tflocal"
	@echo "  destroy     terraform destroy via tflocal"
	@echo "  fmt         Format Terraform files and Python with Black"
	@echo "  validate    terraform validate"
	@echo "  test        Run pytest unit tests"
	@echo "  lint        Run black --check + flake8 on janitor/"
	@echo "  clean       Remove .terraform, __pycache__, tfstate, reports"
	@echo "  dev         Install dev dependencies + pre-commit hooks"

localstack:
	docker run --rm -d --name localstack -p 4566:4566 -e SERVICES=ec2,s3,sts,iam -e AWS_DEFAULT_REGION=us-east-1 localstack/localstack:4.0.0

localstack-stop:
	docker stop localstack

setup:
	pip install -r janitor/requirements.txt

init:
	cd terraform && tflocal init

plan:
	cd terraform && tflocal plan

apply:
	cd terraform && tflocal apply -auto-approve

destroy:
	cd terraform && tflocal destroy -auto-approve

fmt:
	cd terraform && terraform fmt -recursive
	black janitor/

validate:
	cd terraform && terraform validate

test:
	cd janitor && python -m pytest tests/ -v --tb=short

lint:
	flake8 janitor/ --max-line-length=100
	black --check janitor/

clean:
	-rm -rf terraform/.terraform
	-rm -f terraform/terraform.tfstate*
	-find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	-rm -rf .pytest_cache reports/

dev: setup
	@echo "pre-commit install (requires .pre-commit-config.yaml)"

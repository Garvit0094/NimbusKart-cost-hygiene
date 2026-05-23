#!/usr/bin/env python3
"""NimbusKart Cost Janitor - scans LocalStack resources for orphans and waste."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import boto3

from constants import (
    REGION,
    LOCALSTACK_ENDPOINT,
    ACCOUNT_ID,
    EBS_COST_PER_GB_MONTH,
    EIP_UNASSOCIATED_COST_MONTH,
    EC2_STOPPED_ROOT_GB,
    REQUIRED_TAGS,
    STOPPED_DAYS_THRESHOLD,
)

logger = logging.getLogger("janitor")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def get_session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id="fake",
        aws_secret_access_key="fake",
        region_name=REGION,
    )


def get_client(service: str, session: boto3.Session | None = None) -> Any:
    if session is None:
        session = get_session()
    return session.client(service, endpoint_url=LOCALSTACK_ENDPOINT)


def scan_unattached_volumes(ec2_client: Any, findings: list[dict[str, Any]]) -> None:
    paginator = ec2_client.get_paginator("describe_volumes")
    for page in paginator.paginate():
        for vol in page.get("Volumes", []):
            if vol.get("Attachments"):
                continue
            tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
            age = (datetime.now(timezone.utc) - vol["CreateTime"]).days
            cost = round(vol["Size"] * EBS_COST_PER_GB_MONTH, 2)
            findings.append(
                {
                    "resource_id": vol["VolumeId"],
                    "resource_type": "ebs_volume",
                    "reason": "Unattached EBS volume",
                    "age_days": age,
                    "estimated_monthly_cost_usd": cost,
                    "tags": tags,
                    "suggested_action": "Delete or attach to a running instance",
                    "safe_to_auto_delete": tags.get("Protected", "").lower() != "true",
                }
            )
            logger.info(
                "Unattached volume: %s (%d GB, $%.2f/mo)", vol["VolumeId"], vol["Size"], cost
            )


def scan_stopped_instances(
    ec2_client: Any, findings: list[dict[str, Any]], threshold_days: int = STOPPED_DAYS_THRESHOLD
) -> None:
    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    ):
        for res in page.get("Reservations", []):
            for inst in res.get("Instances", []):
                launched = inst["LaunchTime"]
                age = (datetime.now(timezone.utc) - launched).days
                if age < threshold_days:
                    continue
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                cost = round(EC2_STOPPED_ROOT_GB * EBS_COST_PER_GB_MONTH, 2)
                findings.append(
                    {
                        "resource_id": inst["InstanceId"],
                        "resource_type": "ec2_instance",
                        "reason": f"Stopped {age} days (threshold: {threshold_days})",
                        "age_days": age,
                        "estimated_monthly_cost_usd": cost,
                        "tags": tags,
                        "suggested_action": "Start or terminate the instance",
                        "safe_to_auto_delete": tags.get("Protected", "").lower() != "true",
                    }
                )
                logger.info("Stopped instance: %s (%d days)", inst["InstanceId"], age)


def scan_unassociated_eips(ec2_client: Any, findings: list[dict[str, Any]]) -> None:
    resp = ec2_client.describe_addresses()
    for addr in resp.get("Addresses", []):
        if "InstanceId" in addr or "NetworkInterfaceId" in addr:
            continue
        tags = {t["Key"]: t["Value"] for t in addr.get("Tags", [])}
        findings.append(
            {
                "resource_id": addr["AllocationId"],
                "resource_type": "elastic_ip",
                "reason": "Elastic IP not associated with any resource",
                "age_days": 0,
                "estimated_monthly_cost_usd": EIP_UNASSOCIATED_COST_MONTH,
                "tags": tags,
                "suggested_action": "Release the Elastic IP",
                "safe_to_auto_delete": tags.get("Protected", "").lower() != "true",
            }
        )
        logger.info(
            "Unassociated EIP: %s ($%.2f/mo)", addr["AllocationId"], EIP_UNASSOCIATED_COST_MONTH
        )


def scan_missing_tags(ec2_client: Any, s3_client: Any, findings: list[dict[str, Any]]) -> None:
    inst_paginator = ec2_client.get_paginator("describe_instances")
    for page in inst_paginator.paginate():
        for res in page.get("Reservations", []):
            for inst in res.get("Instances", []):
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                missing = [t for t in REQUIRED_TAGS if t not in tags]
                if missing:
                    findings.append(
                        {
                            "resource_id": inst["InstanceId"],
                            "resource_type": "ec2_instance",
                            "reason": f"Missing required tags: {', '.join(missing)}",
                            "age_days": (datetime.now(timezone.utc) - inst["LaunchTime"]).days,
                            "estimated_monthly_cost_usd": round(
                                EC2_STOPPED_ROOT_GB * EBS_COST_PER_GB_MONTH, 2
                            ),
                            "tags": tags,
                            "suggested_action": f"Add missing tags: {', '.join(missing)}",
                            "safe_to_auto_delete": False,
                        }
                    )

    vol_paginator = ec2_client.get_paginator("describe_volumes")
    for page in vol_paginator.paginate():
        for vol in page.get("Volumes", []):
            tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
            missing = [t for t in REQUIRED_TAGS if t not in tags]
            if missing:
                findings.append(
                    {
                        "resource_id": vol["VolumeId"],
                        "resource_type": "ebs_volume",
                        "reason": f"Missing required tags: {', '.join(missing)}",
                        "age_days": (datetime.now(timezone.utc) - vol["CreateTime"]).days,
                        "estimated_monthly_cost_usd": round(vol["Size"] * EBS_COST_PER_GB_MONTH, 2),
                        "tags": tags,
                        "suggested_action": f"Add missing tags: {', '.join(missing)}",
                        "safe_to_auto_delete": False,
                    }
                )

    try:
        buckets = s3_client.list_buckets()
        for bucket in buckets.get("Buckets", []):
            try:
                tagging = s3_client.get_bucket_tagging(Bucket=bucket["Name"])
                tags = {t["Key"]: t["Value"] for t in tagging.get("TagSet", [])}
            except s3_client.exceptions.ClientError:
                tags = {}
            missing = [t for t in REQUIRED_TAGS if t not in tags]
            if missing:
                findings.append(
                    {
                        "resource_id": bucket["Name"],
                        "resource_type": "s3_bucket",
                        "reason": f"Missing required tags: {', '.join(missing)}",
                        "age_days": (datetime.now(timezone.utc) - bucket["CreationDate"]).days,
                        "estimated_monthly_cost_usd": 0.0,
                        "tags": tags,
                        "suggested_action": f"Add missing tags: {', '.join(missing)}",
                        "safe_to_auto_delete": False,
                    }
                )
    except Exception:
        logger.warning("Could not scan S3 buckets for missing tags", exc_info=True)


def delete_unattached_volumes(
    ec2_client: Any, findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    deleted: list[dict[str, Any]] = []
    for f in findings:
        if f["resource_type"] != "ebs_volume" or not f["safe_to_auto_delete"]:
            continue
        try:
            ec2_client.delete_volume(VolumeId=f["resource_id"])
            logger.info("Deleted unattached volume %s", f["resource_id"])
            deleted.append(f)
        except Exception as e:
            logger.error("Failed to delete volume %s: %s", f["resource_id"], e)
    return deleted


def delete_unassociated_eips(
    ec2_client: Any, findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    released: list[dict[str, Any]] = []
    for f in findings:
        if f["resource_type"] != "elastic_ip" or not f["safe_to_auto_delete"]:
            continue
        try:
            ec2_client.release_address(AllocationId=f["resource_id"])
            logger.info("Released Elastic IP %s", f["resource_id"])
            released.append(f)
        except Exception as e:
            logger.error("Failed to release EIP %s: %s", f["resource_id"], e)
    return released


def generate_report(findings: list[dict[str, Any]], output_dir: str) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    total_cost = round(sum(f["estimated_monthly_cost_usd"] for f in findings), 2)

    report = {
        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        "account_id": ACCOUNT_ID,
        "region": REGION,
        "summary": {
            "total_orphans": len(findings),
            "estimated_monthly_waste_usd": total_cost,
        },
        "findings": findings,
    }

    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("JSON report written to %s", json_path)

    md_path = os.path.join(output_dir, "report.md")
    with open(md_path, "w") as f:
        f.write("# NimbusKart Cost Hygiene Report\n\n")
        f.write(f"- **Scan timestamp:** {report['scan_timestamp']}\n")
        f.write(f"- **Account ID:** {report['account_id']}\n")
        f.write(f"- **Region:** {report['region']}\n")
        f.write(f"- **Total orphans:** {report['summary']['total_orphans']}\n")
        f.write(f"- **Monthly waste:** ${report['summary']['estimated_monthly_waste_usd']:.2f}\n\n")
        f.write("## Findings\n\n")
        f.write("| Resource ID | Type | Reason | Age (days) | Cost/mo | Safe to Delete |\n")
        f.write("|------------|------|--------|-----------|---------|----------------|\n")
        for finding in findings:
            safe = "Yes" if finding["safe_to_auto_delete"] else "No (protected)"
            f.write(
                f"| {finding['resource_id']} "
                f"| {finding['resource_type']} "
                f"| {finding['reason']} "
                f"| {finding['age_days']} "
                f"| ${finding['estimated_monthly_cost_usd']:.2f} "
                f"| {safe} |\n"
            )
    logger.info("Markdown report written to %s", md_path)

    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NimbusKart Cost Janitor - scan AWS resources for orphaned and wasted resources"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run scan without making changes (default: on)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        default=False,
        help="Delete orphaned resources (disables dry-run)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Directory to write reports into",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--threshold-days",
        type=int,
        default=STOPPED_DAYS_THRESHOLD,
        help=(
            f"Days after which a stopped instance is considered orphaned "
            f"(default: {STOPPED_DAYS_THRESHOLD})"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    if args.delete:
        args.dry_run = False

    logger.info("NimbusKart Cost Janitor starting (dry-run=%s)", args.dry_run)

    session = get_session()
    ec2 = get_client("ec2", session)
    s3 = get_client("s3", session)

    findings: list[dict[str, Any]] = []

    scan_unattached_volumes(ec2, findings)
    scan_stopped_instances(ec2, findings, args.threshold_days)
    scan_unassociated_eips(ec2, findings)
    scan_missing_tags(ec2, s3, findings)

    if not args.dry_run:
        n_vol = len(delete_unattached_volumes(ec2, findings))
        n_eip = len(delete_unassociated_eips(ec2, findings))
        logger.info("Deleted %d volumes, released %d EIPs", n_vol, n_eip)
        findings = [f for f in findings if f["safe_to_auto_delete"]]

    total_cost = round(sum(f["estimated_monthly_cost_usd"] for f in findings), 2)
    logger.info("Found %d orphan(s), estimated monthly waste $%.2f", len(findings), total_cost)

    json_path, md_path = generate_report(findings, args.output_dir)

    if findings and args.dry_run:
        logger.warning("Orphans exist in dry-run mode → exit code 1")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

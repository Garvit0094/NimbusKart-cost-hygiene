"""Unit tests for NimbusKart Cost Janitor."""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from janitor import (  # noqa: E402
    scan_unattached_volumes,
    scan_stopped_instances,
    scan_unassociated_eips,
    scan_missing_tags,
    delete_unattached_volumes,
    generate_report,
    parse_args,
    main,
)
from constants import (  # noqa: E402
    EBS_COST_PER_GB_MONTH,
    EIP_UNASSOCIATED_COST_MONTH,
    STOPPED_DAYS_THRESHOLD,
)


def make_vol(
    vol_id: str,
    size: int = 10,
    days_old: int = 30,
    attached: bool = False,
    tags: list | None = None,
) -> dict:
    vol = {
        "VolumeId": vol_id,
        "Size": size,
        "CreateTime": datetime.now(timezone.utc) - timedelta(days=days_old),
        "Attachments": [{"InstanceId": "i-xxx", "State": "attached"}] if attached else [],
        "Tags": tags or [{"Key": "Name", "Value": "test"}],
    }
    return vol


def test_scan_unattached_volumes_finds_orphans():
    ec2 = MagicMock()
    ec2.get_paginator.return_value.paginate.return_value = [
        {"Volumes": [make_vol("vol-orphan", attached=False)]}
    ]
    findings: list = []
    scan_unattached_volumes(ec2, findings)
    assert len(findings) == 1
    f = findings[0]
    assert f["resource_id"] == "vol-orphan"
    assert f["resource_type"] == "ebs_volume"
    assert f["estimated_monthly_cost_usd"] == round(10 * EBS_COST_PER_GB_MONTH, 2)
    assert f["safe_to_auto_delete"] is True


def test_scan_unattached_volumes_skips_attached():
    ec2 = MagicMock()
    ec2.get_paginator.return_value.paginate.return_value = [
        {"Volumes": [make_vol("vol-attached", attached=True)]}
    ]
    findings: list = []
    scan_unattached_volumes(ec2, findings)
    assert len(findings) == 0


def test_scan_unattached_volumes_empty():
    ec2 = MagicMock()
    ec2.get_paginator.return_value.paginate.return_value = [{"Volumes": []}]
    findings: list = []
    scan_unattached_volumes(ec2, findings)
    assert len(findings) == 0


def test_scan_stopped_instances_finds_old():
    ec2 = MagicMock()
    ec2.get_paginator.return_value.paginate.return_value = [
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-stopped-old",
                            "State": {"Name": "stopped"},
                            "LaunchTime": datetime.now(timezone.utc) - timedelta(days=30),
                            "Tags": [],
                        }
                    ]
                }
            ]
        }
    ]
    findings: list = []
    scan_stopped_instances(ec2, findings)
    assert len(findings) == 1
    assert findings[0]["resource_id"] == "i-stopped-old"


def test_scan_stopped_instances_skips_recent():
    ec2 = MagicMock()
    ec2.get_paginator.return_value.paginate.return_value = [
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-stopped-recent",
                            "State": {"Name": "stopped"},
                            "LaunchTime": datetime.now(timezone.utc) - timedelta(days=5),
                            "Tags": [],
                        }
                    ]
                }
            ]
        }
    ]
    findings: list = []
    scan_stopped_instances(ec2, findings)
    assert len(findings) == 0


def test_scan_unassociated_eips():
    ec2 = MagicMock()
    ec2.describe_addresses.return_value = {
        "Addresses": [{"AllocationId": "eipalloc-xyz", "PublicIp": "1.2.3.4", "Tags": []}]
    }
    findings: list = []
    scan_unassociated_eips(ec2, findings)
    assert len(findings) == 1
    assert findings[0]["estimated_monthly_cost_usd"] == EIP_UNASSOCIATED_COST_MONTH


def test_scan_unassociated_eips_skips_associated():
    ec2 = MagicMock()
    ec2.describe_addresses.return_value = {
        "Addresses": [
            {
                "AllocationId": "eipalloc-used",
                "PublicIp": "5.6.7.8",
                "InstanceId": "i-abc",
                "Tags": [],
            }
        ]
    }
    findings: list = []
    scan_unassociated_eips(ec2, findings)
    assert len(findings) == 0


def test_scan_missing_tags_on_instance():
    inst_paginator = MagicMock()
    inst_paginator.paginate.return_value = [
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-notags",
                            "LaunchTime": datetime.now(timezone.utc),
                            "State": {"Name": "running"},
                            "Tags": [],
                        }
                    ]
                }
            ]
        }
    ]
    vol_paginator = MagicMock()
    vol_paginator.paginate.return_value = [{"Volumes": []}]

    ec2 = MagicMock()
    ec2.get_paginator.side_effect = lambda name: {
        "describe_instances": inst_paginator,
        "describe_volumes": vol_paginator,
    }.get(name, MagicMock())

    s3 = MagicMock()
    s3.list_buckets.return_value = {"Buckets": []}

    findings: list = []
    scan_missing_tags(ec2, s3, findings)
    ids = {f["resource_id"] for f in findings}
    assert "i-notags" in ids


def test_protected_tag_respected():
    ec2 = MagicMock()
    ec2.get_paginator.return_value.paginate.return_value = [
        {
            "Volumes": [
                {
                    "VolumeId": "vol-protected",
                    "Size": 10,
                    "CreateTime": datetime.now(timezone.utc) - timedelta(days=10),
                    "Attachments": [],
                    "Tags": [
                        {"Key": "Protected", "Value": "true"},
                        {"Key": "Name", "Value": "protected"},
                    ],
                }
            ]
        }
    ]
    findings: list = []
    scan_unattached_volumes(ec2, findings)
    assert len(findings) == 1
    assert findings[0]["safe_to_auto_delete"] is False


def test_delete_unattached_volumes_skips_protected():
    findings = [
        {
            "resource_id": "vol-protected",
            "resource_type": "ebs_volume",
            "safe_to_auto_delete": False,
            "estimated_monthly_cost_usd": 0.0,
            "age_days": 1,
            "reason": "",
            "tags": {},
            "suggested_action": "",
        }
    ]
    ec2 = MagicMock()
    deleted = delete_unattached_volumes(ec2, findings)
    assert len(deleted) == 0
    ec2.delete_volume.assert_not_called()


def test_generate_report_creates_both_files():
    findings = [
        {
            "resource_id": "vol-test",
            "resource_type": "ebs_volume",
            "reason": "Unattached",
            "age_days": 10,
            "estimated_monthly_cost_usd": 0.8,
            "tags": {},
            "suggested_action": "Delete",
            "safe_to_auto_delete": True,
        }
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path, md_path = generate_report(findings, tmpdir)
        assert os.path.exists(json_path)
        assert os.path.exists(md_path)
        with open(json_path) as f:
            report = json.load(f)
            assert report["summary"]["total_orphans"] == 1
            assert report["summary"]["estimated_monthly_waste_usd"] == 0.8


def test_parse_args_defaults():
    args = parse_args(["--dry-run"])
    assert args.dry_run is True
    assert args.delete is False
    assert args.output_dir == "reports"
    assert args.threshold_days == STOPPED_DAYS_THRESHOLD


def test_parse_args_delete():
    args = parse_args(["--delete"])
    assert args.delete is True


def test_main_no_orphans():
    with patch("janitor.scan_unattached_volumes"):
        with patch("janitor.scan_stopped_instances"):
            with patch("janitor.scan_unassociated_eips"):
                with patch("janitor.scan_missing_tags"):
                    with patch("janitor.generate_report") as mock_gr:
                        mock_gr.return_value = ("r.json", "r.md")
                        rc = main(["--dry-run"])
                        assert rc == 0


def test_main_orphans_dry_run():
    with patch("janitor.scan_unattached_volumes") as mock_suv:

        def append_finding(_ec2, findings):
            findings.append({"resource_id": "vol-x", "estimated_monthly_cost_usd": 0.5})

        mock_suv.side_effect = append_finding
        with patch("janitor.scan_stopped_instances"):
            with patch("janitor.scan_unassociated_eips"):
                with patch("janitor.scan_missing_tags"):
                    with patch("janitor.generate_report") as mock_gr:
                        mock_gr.return_value = ("r.json", "r.md")
                        rc = main(["--dry-run"])
                        assert rc == 1


def test_main_delete_mode_clears_findings():
    with patch("janitor.scan_unattached_volumes") as mock_suv:

        def append_finding(_ec2, findings):
            findings.append(
                {
                    "resource_id": "vol-deletable",
                    "resource_type": "ebs_volume",
                    "safe_to_auto_delete": True,
                    "estimated_monthly_cost_usd": 0.5,
                    "age_days": 1,
                    "reason": "",
                    "tags": {},
                    "suggested_action": "",
                }
            )

        mock_suv.side_effect = append_finding
        with patch("janitor.scan_stopped_instances"):
            with patch("janitor.scan_unassociated_eips"):
                with patch("janitor.scan_missing_tags"):
                    with patch("janitor.delete_unattached_volumes") as mock_del:
                        mock_del.return_value = [{"resource_id": "vol-deletable"}]
                        with patch("janitor.delete_unassociated_eips") as mock_eip:
                            mock_eip.return_value = []
                            with patch("janitor.generate_report") as mock_gr:
                                mock_gr.return_value = ("r.json", "r.md")
                                rc = main(["--delete"])
                                assert rc == 0

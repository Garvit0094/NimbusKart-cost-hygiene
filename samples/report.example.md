# NimbusKart Cost Hygiene Report

- **Scan timestamp:** 2026-05-21T12:00:00+00:00
- **Account ID:** 000000000000
- **Region:** us-east-1
- **Total orphans:** 2
- **Monthly waste:** $4.36

## Findings

| Resource ID | Type | Reason | Age (days) | Cost/mo | Safe to Delete |
|------------|------|--------|-----------|---------|----------------|
| vol-ffffffff | ebs_volume | Unattached EBS volume | 45 | $0.80 | Yes |
| eipalloc-ffffffff | elastic_ip | Elastic IP not associated with any resource | 0 | $3.60 | Yes |

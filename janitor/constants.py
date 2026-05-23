from typing import Final

REGION: Final[str] = "us-east-1"
LOCALSTACK_ENDPOINT: Final[str] = "http://localhost:4566"
ACCOUNT_ID: Final[str] = "000000000000"

REQUIRED_TAGS: Final[list[str]] = ["Project", "Environment", "Owner"]

STOPPED_DAYS_THRESHOLD: Final[int] = 14

EBS_COST_PER_GB_MONTH: Final[float] = 0.08

EIP_UNASSOCIATED_COST_MONTH: Final[float] = 3.60

EC2_STOPPED_ROOT_GB: Final[int] = 8

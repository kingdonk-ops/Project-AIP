"""Create the dev object-store bucket if it is missing (compose ``object-store-init``, STACK-05).

Runs in the API image with the same ``OBJECT_STORE_*`` variables as the API, so the bucket the API
writes to is the one created here. Idempotent; exits non-zero only if the bucket cannot be made.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import boto3  # pyright: ignore[reportMissingTypeStubs]
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]
from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]


def main() -> int:
    bucket = os.environ.get("OBJECT_STORE_BUCKET", "aip")
    region = os.environ.get("OBJECT_STORE_REGION", "us-east-1")
    s3: Any = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=os.environ["OBJECT_STORE_ENDPOINT_URL"],
        region_name=region,
        aws_access_key_id=os.environ["OBJECT_STORE_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["OBJECT_STORE_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"bucket {bucket} exists")
        return 0
    except ClientError:
        pass
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket)
    else:
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
    print(f"bucket {bucket} created")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Runs inside LocalStack once S3 is ready: create the contracts bucket.
set -euo pipefail
awslocal s3 mb "s3://${CONTRACTS_BUCKET:-contracts}"

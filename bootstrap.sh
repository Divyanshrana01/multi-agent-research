#!/bin/bash
# this script sets up the s3 bucket + dynamodb table that terraform needs
# BEFORE we can run terraform itself (terraform's backend config in main.tf
# points at these, so they have to exist first). run this once per aws account.
set -e  # stop the script if any command fails

# use region passed as first arg, otherwise default to us-east-1
REGION=${1:-us-east-1}
BUCKET="research-agent-tfstate"
TABLE="research-agent-tf-locks"

echo "Creating S3 bucket: $BUCKET in region: $REGION"

# us-east-1 is special in aws - it doesn't want a LocationConstraint,
# every other region needs one, so we branch on that here
if [ "$REGION" = "us-east-1" ]; then
  aws s3api create-bucket \
    --bucket "$BUCKET" \
    --region "$REGION" 2>/dev/null && echo "Bucket created." || echo "Bucket already exists, continuing."
else
  aws s3api create-bucket \
    --bucket "$BUCKET" \
    --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" 2>/dev/null && echo "Bucket created." || echo "Bucket already exists, continuing."
fi

# versioning = if state file ever gets corrupted/overwritten we can roll back
echo "Enabling versioning on S3 bucket..."
aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

# state file can have secrets in it, so make sure nobody outside can reach the bucket
echo "Blocking public access on S3 bucket..."
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# encrypt the state file at rest too, extra safety since it can hold secrets
echo "Enabling server-side encryption on S3 bucket..."
aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# this table is how terraform "locks" the state file so two people
# running apply at the same time don't corrupt it
echo "Creating DynamoDB table for Terraform state locking: $TABLE"
aws dynamodb create-table \
  --table-name "$TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null && echo "DynamoDB table created." || echo "DynamoDB table already exists, continuing."

echo ""
echo "Bootstrap complete."
echo "  S3 bucket  : $BUCKET (versioned, encrypted, private)"
echo "  DynamoDB   : $TABLE (state locking)"
echo ""
echo "Next step: cd terraform && terraform init && terraform apply"

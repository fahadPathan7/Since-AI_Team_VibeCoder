#!/usr/bin/env bash
# Deploy the dashboard and API to AWS: ./infra/deploy.sh        Remove everything: ./infra/deploy.sh destroy
set -euo pipefail

# Paths and the AWS profile to use (export AWS_PROFILE=... to choose one)
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
TF="$HERE/terraform"
TAG="$(date +%Y%m%d%H%M%S)"

# Stop early if a tool or the AWS login is missing
for tool in aws terraform docker; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool'. See infra/README.md"; exit 1; }
done
aws sts get-caller-identity --query Arn --output text >/dev/null || { echo "Not logged in to AWS. Run 'aws configure' or 'aws sso login' first."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop first."; exit 1; }
echo "AWS account: $(aws sts get-caller-identity --query Account --output text)"

cd "$TF"
terraform init -input=false >/dev/null

# Removing everything
if [ "${1:-}" = "destroy" ]; then
  terraform destroy -auto-approve
  exit 0
fi

# The dashboard data must exist before upload
[ -f "$ROOT/dashboard/web/data/dashboard.json" ] || (cd "$ROOT" && python -m dashboard.build_data)

# Step 1: the image registry
terraform apply -input=false -auto-approve -target=aws_ecr_repository.api -target=aws_ecr_lifecycle_policy.api
REPO="$(terraform output -raw ecr_repository_url)"
REGION="$(echo "$REPO" | cut -d. -f4)"

# Step 2: build the API image for ARM Lambda and push it
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
docker buildx build --platform linux/arm64 --provenance=false -f "$ROOT/dashboard/Dockerfile" -t "$REPO:$TAG" --push "$ROOT"
DIGEST="$(aws ecr describe-images --region "$REGION" --repository-name "${REPO#*/}" --image-ids imageTag="$TAG" --query 'imageDetails[0].imageDigest' --output text)"

# Step 3: everything else, using the exact image just pushed
terraform apply -input=false -auto-approve -var "image_uri=$REPO@$DIGEST"

# Step 4: make CloudFront serve the new page files at once
aws cloudfront create-invalidation --distribution-id "$(terraform output -raw distribution_id)" --paths "/*" >/dev/null

echo
echo "Dashboard: $(terraform output -raw site_url)"
echo "API docs:  $(terraform output -raw api_docs_url)"
echo "A new CloudFront address can take a few minutes to start working."

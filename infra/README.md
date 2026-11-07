# Hosting on AWS

Terraform for the dashboard and API. No Route 53 and no custom domain: the site gets a CloudFront address such as `https://d1234abcd.cloudfront.net` with HTTPS.

```text
Browser ──HTTPS──> CloudFront ──/*──────> S3 bucket (the page, private, read only by CloudFront)
                              └─/api/*──> Lambda function URL (API, container image, refuses requests without CloudFront's secret header)
Browser ──signed PUT──> S3 runs bucket (uploads and results, deleted after one day)
```

| Resource | Purpose |
|---|---|
| CloudFront distribution | One HTTPS address for the page and the API. Optional password prompt |
| S3 web bucket | The page, served only through CloudFront |
| Lambda function (container) | The API and forecast runs, 3 GB memory, arm64 |
| ECR repository | The API image |
| S3 runs bucket | Uploaded files and results, deleted after one day |
| IAM role, CloudWatch logs | Permissions and logs for the function, logs kept 14 days |

Uploads go straight from the browser to S3 with a signed URL, because `inputs.csv` (39 MB) is larger than Lambda's 6 MB request limit. A run then starts in the background, and the page polls for progress.

**Cost:** with light use, a few dollars a month or less, mostly the ECR image (about 0.4 GB) and requests. Everything scales to zero when idle. `./infra/deploy.sh destroy` removes it all.

**Data:** the image contains the code, the trained model and the precomputed dashboard data. It holds no input data, and the site never shows spot prices. Files uploaded through **Run a forecast** are deleted after one day.

## 1. Install the tools (once)

```bash
brew install awscli terraform
```

Docker Desktop must be installed and running.

## 2. Log in to AWS

Choose one of these.

**A. Access keys** (simplest, for a personal account)

1. In the AWS console, open **IAM → Users → Create user**, for example `deployer`.
2. Attach the policy **AdministratorAccess**. A narrower policy needs at least S3, CloudFront, Lambda, ECR, IAM and CloudWatch Logs.
3. Open the user, then **Security credentials → Create access key → Command Line Interface (CLI)**, and copy both keys.
4. Run:

```bash
aws configure
# AWS Access Key ID:     <paste>
# AWS Secret Access Key: <paste>
# Default region name:   eu-north-1
# Default output format: json
```

**B. IAM Identity Center (SSO)**, if your organisation uses it:

```bash
aws configure sso          # start URL and region from your administrator
aws sso login --profile <profile-name>
export AWS_PROFILE=<profile-name>
```

Check the login:

```bash
aws sts get-caller-identity
```

## 3. Optional: a password for the site

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
```

Then set `basic_auth_password` in that file. Leave it empty for an open site. The region can be changed there too, and the default is `eu-north-1` (Stockholm).

## 4. Deploy

From the `submission` folder:

```bash
./infra/deploy.sh
```

The script:

1. checks the tools and the login
2. creates the ECR repository
3. builds the API image for arm64 and pushes it
4. creates everything else
5. clears the CloudFront cache

It prints the site address at the end. The first deploy takes about 5–10 minutes, mostly CloudFront, and a new address can take a few more minutes to answer.

Run the same command again after any change. It builds a new image and updates only what changed.

## 5. Remove everything

```bash
./infra/deploy.sh destroy
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Not logged in to AWS` | Repeat step 2. With SSO, run `aws sso login` again, because sessions expire |
| `Docker is not running` | Start Docker Desktop and wait until it says it is running |
| The page loads but the API returns 403 | Wait a few minutes after the first deploy, then run `./infra/deploy.sh` again |
| A run fails | See the function's logs: CloudWatch → Log groups → `/aws/lambda/imbalance-watch-…-api` |
| Lambda memory error on a new account | Set `lambda_memory_mb = 2048` in `terraform.tfvars` and deploy again |

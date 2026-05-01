# Local Setup Guide

Everything you need to go from zero to a running local environment on Ubuntu 24.04 LTS.

---

## Step 1 — System dependencies

```bash
# Update package index
sudo apt update

# AWS CLI
sudo apt install awscli -y
aws --version  # expected: aws-cli/2.x.x

# Python 3.12 + pip + venv
sudo apt install python3-pip python3-venv -y
python3 --version  # expected: Python 3.12.x

# Git (likely already installed)
sudo apt install git -y
git --version
```

---

## Step 2 — Terraform

```bash
sudo apt-get install -y gnupg software-properties-common curl

wget -O- https://apt.releases.hashicorp.com/gpg | \
  gpg --dearmor | \
  sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null

echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/hashicorp.list

sudo apt update && sudo apt install terraform -y
terraform --version  # expected: Terraform v1.x.x
```

---

## Step 3 — AWS CLI configuration

You need an IAM user with programmatic access. Do NOT use your root account.

```bash
aws configure
```

You'll be prompted for:
```
AWS Access Key ID [None]: YOUR_ACCESS_KEY_ID
AWS Secret Access Key [None]: YOUR_SECRET_ACCESS_KEY
Default region name [None]: us-east-1
Default output format [None]: json
```

Verify it works:
```bash
aws sts get-caller-identity
```

Expected output:
```json
{
    "UserId": "AIDA...",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/your-iam-user"
}
```

If you see this, your credentials are configured correctly.

---

## Step 4 — Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/fraudshield-payment-api.git
cd fraudshield-payment-api
```

---

## Step 5 — Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate

# Install dependencies for both Lambdas
pip install -r src/fraud_scorer/requirements.txt
pip install -r src/transaction_processor/requirements.txt
pip install pytest flake8  # for testing and linting
```

---

## Step 6 — Run tests locally (before deploying anything)

```bash
pytest tests/ -v
```

All tests should pass before you run `terraform apply`.

---

## Step 7 — Deploy to AWS

```bash
cd terraform

# Initialize Terraform (downloads AWS provider)
terraform init

# Preview what will be created — READ THIS carefully
terraform plan

# Deploy
terraform apply
# Type 'yes' when prompted
```

Terraform will output your API Gateway URL when complete:
```
Outputs:
api_gateway_url = "https://abc123.execute-api.us-east-1.amazonaws.com/prod"
```

---

## Step 8 — Test the deployed API

```bash
# Save your API URL
API_URL="https://YOUR_ID.execute-api.us-east-1.amazonaws.com/prod"

# Test 1: Normal transaction (should APPROVE)
curl -X POST $API_URL/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "card_001",
    "amount": 150.00,
    "country": "MX",
    "merchant": "Costco MX"
  }'

# Expected: {"decision": "APPROVE", "score": 0, "transaction_id": "..."}

# Test 2: High-risk transaction (should DECLINE)
curl -X POST $API_URL/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "card_002",
    "amount": 9500.00,
    "country": "NG",
    "merchant": "Unknown Merchant"
  }'

# Expected: {"decision": "DECLINE", "score": 85, "reason": "High risk score"}
```

---

## Step 9 — View logs in CloudWatch

```bash
# Tail fraud scorer logs
aws logs tail /aws/lambda/fraudshield-fraud-scorer --follow

# Tail transaction processor logs
aws logs tail /aws/lambda/fraudshield-transaction-processor --follow
```

---

## Tear down (avoid unexpected AWS charges)

```bash
cd terraform
terraform destroy
# Type 'yes' when prompted
```

This removes all AWS resources created by the project. Always run this when you're done testing to stay within Free Tier limits.

---

## Free Tier limits reference

| Service | Free Tier | FraudShield usage |
|---|---|---|
| Lambda | 1M requests/month, 400k GB-seconds | Well within for testing |
| API Gateway | 1M API calls/month (12 months) | Well within for testing |
| SQS | 1M requests/month | Well within for testing |
| DynamoDB | 25 GB storage, 25 RCU/WCU | Well within for testing |
| CloudWatch | 5 GB log data/month | Well within for testing |

Running this project for testing purposes should cost $0 if you're within the first 12 months of your AWS account and you destroy resources when not in use.

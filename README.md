# FraudShield Payment API

> Real-time payment fraud detection engine built on AWS serverless infrastructure.  
> A hands-on cloud implementation project demonstrating end-to-end integration architecture, CI/CD automation, and fraud decisioning patterns from production banking environments.

---

## Why This Project Exists

I previously have migrated fraud prevention systems from IBM Mainframe to Actimize IFM, validating 500 TPS under stress, and maintaining ≤1.6s SLA on real-time authorization APIs — I wanted to translate that domain knowledge into a cloud-native implementation using AWS serverless and modern DevOps tooling.

This is not a tutorial project. Every architectural decision here maps to a real problem I've solved in production.

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │           GitHub Actions (CI/CD)         │
                        │   test → lint → terraform plan → deploy  │
                        └──────────────────┬──────────────────────┘
                                           │ push to main
                                           ▼
POST /v1/transaction ──► API Gateway ──► Lambda: fraud-scorer
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                         score > 70               score ≤ 70
                              │                         │
                         DECLINE ◄──────────    SQS: transactions-queue
                         (response)                     │
                                                        ▼
                                           Lambda: transaction-processor
                                                        │
                                                        ▼
                                                   DynamoDB
                                              (transactions table)
                                                        │
                                                        ▼
                                              CloudWatch Logs/Metrics
```

### Why each component

| Component | Role | Architectural Reasoning |
|---|---|---|
| **API Gateway** | HTTP entry point | Decouples client from compute. Handles throttling, auth, and SSL termination — equivalent to the authorization API layer in Actimize IFM integration |
| **Lambda: fraud-scorer** | Real-time decisioning | Stateless, sub-second execution. Applies velocity, amount, and geo risk rules. Mirrors the ≤1.6s SLA constraint from production card authorization |
| **SQS** | Async queue | Absorbs traffic spikes without dropping transactions. Critical for 500 TPS resilience — the processor never gets overwhelmed by burst volume |
| **Lambda: transaction-processor** | Persistence layer | Processes approved transactions from queue, writes to DynamoDB with full audit trail |
| **DynamoDB** | Transaction store | Serverless NoSQL with single-digit millisecond reads. Audit trail for every decisioning event |
| **CloudWatch** | Observability | Structured logs per transaction, metric alarms for error rate spikes and latency breaches |
| **Terraform** | Infrastructure as Code | All AWS resources defined as code, versioned in Git. Reproducible environments, no manual console clicks |
| **GitHub Actions** | CI/CD pipeline | Automated test → deploy on every push to main. Compresses delivery cycle to minutes |

---

## Fraud Scoring Logic

The scorer applies three rule layers, producing a composite risk score (0–100):

```
Score = velocity_score + amount_score + geo_score

velocity_score : transactions from same card in last 60s  →  +40 if > 3 txns
amount_score   : transaction amount vs. historical average →  +35 if > 3x average
geo_score      : country risk tier                         →  +25 if high-risk country

Decision threshold: score > 70 → DECLINE
```

This maps directly to the rule architecture I implemented on Actimize IFM:  
simple, auditable rules that produce a traceable decisioning path — not a black box.

---

## Project Structure

```
fraudshield/
├── README.md
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD pipeline
├── terraform/
│   ├── main.tf                 # API Gateway, Lambda, SQS, DynamoDB
│   ├── variables.tf
│   ├── outputs.tf
│   └── iam.tf                  # Least-privilege IAM roles
├── src/
│   ├── fraud_scorer/
│   │   ├── handler.py          # Lambda entry point
│   │   ├── scorer.py           # Risk scoring engine
│   │   └── requirements.txt
│   └── transaction_processor/
│       ├── handler.py          # Lambda entry point
│       ├── processor.py        # DynamoDB write logic
│       └── requirements.txt
├── tests/
│   ├── test_scorer.py          # Unit tests for scoring rules
│   └── test_processor.py
└── docs/
    ├── ARCHITECTURE.md         # Deep-dive on design decisions
    ├── LOCAL_SETUP.md          # How to run locally with mocked AWS
    └── INTERVIEW_NOTES.md      # Key talking points per component
```

---

## Tech Stack

- **Cloud:** AWS (Lambda, API Gateway, SQS, DynamoDB, CloudWatch, IAM)
- **IaC:** Terraform
- **Runtime:** Python 3.12
- **CI/CD:** GitHub Actions
- **Testing:** pytest
- **Local dev:** AWS SAM CLI / LocalStack (optional)
- **OS:** Ubuntu 24.04 LTS

All tools are open source or AWS Free Tier eligible.

---

## Delivery Phases

| Phase | Focus | Target |
|---|---|---|
| **Phase 1** | Terraform infrastructure — API Gateway + Lambda + SQS + DynamoDB wired up | Week 1 |
| **Phase 2** | Fraud scoring logic + transaction processor code + unit tests | Week 2 |
| **Phase 3** | GitHub Actions CI/CD pipeline — test → deploy on push | Week 3 |
| **Phase 4** | CloudWatch observability + documentation + architecture review | Week 4 |

---

## Getting Started

### Prerequisites

```bash
# AWS CLI
sudo apt install awscli -y
aws configure   # enter your IAM Access Key, Secret, region (us-east-1), output (json)

# Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | \
  sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform -y

# Python
sudo apt install python3-pip python3-venv -y
```

### Deploy infrastructure

```bash
git clone https://github.com/YOUR_USERNAME/fraudshield-payment-api.git
cd fraudshield-payment-api/terraform

terraform init
terraform plan        # review what will be created
terraform apply       # deploy to AWS
```

### Run tests

```bash
cd fraudshield-payment-api
python3 -m venv venv && source venv/bin/activate
pip install -r src/fraud_scorer/requirements.txt pytest
pytest tests/ -v
```

### Test the API

```bash
# Get your API Gateway URL from terraform output
API_URL=$(terraform -chdir=terraform output -raw api_gateway_url)

# Approve scenario
curl -X POST $API_URL/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{"card_id": "card_001", "amount": 150.00, "country": "MX", "merchant": "Amazon MX"}'

# Decline scenario (high-risk country + large amount)
curl -X POST $API_URL/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{"card_id": "card_002", "amount": 9500.00, "country": "NG", "merchant": "Unknown Merchant"}'
```

---

## Key Design Decisions

**Why Lambda over ECS/EC2?**  
For an API that needs sub-second response and variable traffic patterns, Lambda eliminates the need to manage servers and scales to zero when idle — directly relevant to cost efficiency in a fraud engine that has defined peak windows.

**Why SQS between scorer and processor?**  
Synchronous direct invocation couples the two Lambdas. If the processor is slow (DynamoDB write latency spike), it would cascade back to the scorer and blow the SLA. SQS absorbs that — exactly the pattern needed to sustain 500 TPS without cascading failures.

**Why DynamoDB over RDS?**  
Transaction records are write-heavy, read by `card_id` or `transaction_id`, and don't require joins. DynamoDB's partition key model is purpose-built for this access pattern.

**Why Terraform over CDK/SAM?**  
Terraform is cloud-agnostic, widely adopted in enterprise AWS environments, and forces explicit resource definition — no magic abstractions hiding configuration.

---

## Production Patterns Demonstrated

| Pattern | Implementation | Production Equivalent |
|---|---|---|
| Sub-second SLA | Lambda warm start + async SQS handoff | Actimize IFM ≤1.6s authorization |
| Burst resilience | SQS decoupling | 500 TPS stress test buffer |
| Audit trail | DynamoDB + CloudWatch structured logs | Fraud Knowledge Base / production monitoring |
| Zero-downtime deploy | GitHub Actions blue/green via Lambda aliases | Card platform migration without downtime |
| Least privilege | IAM roles per Lambda, no wildcard permissions | Regulatory compliance, EUC governance |

---

## Contributing & Feedback

This project is intentionally open for discussion. If you're from the AWS community or have worked in payment/fraud systems:

- **Architecture feedback:** Open an issue with the `architecture` label
- **Code review:** PRs welcome, especially on the scoring logic
- **War stories:** If you've hit similar SLA constraints or SQS patterns in production, I'd love to compare notes

---

## Author

**Adolfo Mite**  
Fraud Prevention Tech Lead | Payment Infrastructure | AWS Cloud Practitioner  
14+ years @ Banamex / Citibanamex  
[linkedin.com/in/mitelite](https://www.linkedin.com/in/mitelite)

---

*Built as a freelance simulation project to validate cloud-native implementation skills.  
Domain knowledge is production-derived. Cloud implementation is the new layer.*

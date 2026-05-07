# Architecture Deep-Dive

## The Problem This Solves
## this is a test done on msi BRANCH feat/receiver-wallet-screening

A payment transaction needs a fraud decision in under 1.6 seconds — from the moment the card is swiped to the moment the merchant terminal shows "approved" or "declined." That window includes network latency, authentication, and the fraud engine itself.

This constraint is not theoretical. It comes from a production SLA I maintained for 115,000+ daily transactions on the Actimize IFM platform at Citibanamex. Any architecture that can't reason about that window first isn't worth building.

---

## Request Lifecycle (annotated)

```
t=0ms    Client sends POST /v1/transaction
t=5ms    API Gateway receives, validates, forwards to fraud-scorer Lambda
t=15ms   Lambda cold start (first call) OR t=5ms warm execution
t=50ms   Scorer queries DynamoDB for velocity check (card_id last 60s)
t=80ms   Score computed, decision made
t=85ms   If APPROVED: message published to SQS
t=90ms   HTTP 200 response returned to client  ← target ≤ 1.6s, actual ~90ms
         (SQS → processor → DynamoDB happens async, client doesn't wait)
```

The async handoff via SQS is what makes the SLA achievable. The client gets a response the moment the fraud decision is made — not after the transaction is persisted. Persistence is guaranteed by SQS durability, not by blocking the client.

---

## Scoring Engine Design

### Why rule-based, not ML?

ML models are appropriate when patterns are too complex for explicit rules and you have labeled training data. For a demo environment without real transaction history, an explicit rule engine is:

1. **Auditable** — every decision has a traceable reason, which is a regulatory requirement in MX/US banking
2. **Debuggable** — when a false positive occurs, you can explain exactly why
3. **Realistic** — Actimize IFM and Falcon both use hybrid approaches; rule engines remain the backbone

In production you layer ML scores on top of rules, not instead of them.

### Rule design rationale

```python
VELOCITY_THRESHOLD = 3       # txns from same card in 60s
VELOCITY_WEIGHT    = 40      # heaviest weight: velocity is the strongest fraud signal
AMOUNT_MULTIPLIER  = 3.0     # amount > 3x historical avg
AMOUNT_WEIGHT      = 35
HIGH_RISK_COUNTRIES = ["NG", "RO", "UA", "PK", "BD"]
GEO_WEIGHT         = 25
DECLINE_THRESHOLD  = 70
```

Velocity carries the most weight because card testing attacks — where fraudsters validate stolen cards with small sequential transactions — are caught by velocity before amount thresholds are triggered. This mirrors real fraud pattern prioritization.

---

## Infrastructure Decisions

### IAM: Least Privilege per Lambda

Each Lambda has its own IAM role with only the permissions it needs:

```
fraud-scorer role:
  - dynamodb:GetItem (velocity check on transactions table)
  - sqs:SendMessage (approved transactions queue)
  - logs:CreateLogGroup, logs:PutLogEvents

transaction-processor role:
  - sqs:ReceiveMessage, sqs:DeleteMessage
  - dynamodb:PutItem
  - logs:CreateLogGroup, logs:PutLogEvents
```

No Lambda has `dynamodb:*` or `sqs:*`. This is not just security hygiene — in a regulated environment, wildcard permissions are a finding in a compliance audit.

### SQS: Why not EventBridge?

EventBridge is better suited for routing events to multiple consumers based on content. Here we have one producer (scorer) and one consumer (processor) with no routing logic needed. SQS is simpler, cheaper, and has built-in Dead Letter Queue support for failed processing — which maps to how you'd handle a DynamoDB write failure without losing the transaction.

### DynamoDB: Table Design

```
Table: fraudshield-transactions
  Partition key: card_id (String)
  Sort key:      timestamp (String, ISO 8601)
  
GSI: transaction-id-index
  Partition key: transaction_id
```

Query patterns supported:
- All transactions for a card (fraud investigation by card) → partition key scan
- Single transaction lookup (reconciliation, dispute) → GSI on transaction_id
- Time-range for a card (velocity historical analysis) → partition + sort key range

---

## CI/CD Pipeline Logic

```yaml
on: push to main

jobs:
  test:     pytest → must pass before any deployment
  lint:     flake8 Python checks
  plan:     terraform plan → outputs what will change (no apply yet)
  deploy:   terraform apply → only if test + lint + plan succeed
```

The pipeline enforces that no code reaches AWS without passing tests. This directly replicates the governance I implemented for Python ETL delivery at Banamex — where we compressed the cycle from 8 to 4 weeks by automating validation gates instead of running them manually.

---

## What This Architecture Does NOT Cover (and why)

| Missing piece | Why omitted | Production equivalent |
|---|---|---|
| API authentication (API Keys / JWT) | Scope: focus on fraud logic, not authN | Would add Cognito or Lambda authorizer |
| Multi-region failover | Single region sufficient for demo | Production: Route 53 + us-east-1 + us-west-2 |
| ML fraud model | Requires labeled dataset | Would integrate SageMaker endpoint as additional scorer |
| Card tokenization | Out of scope | PCI-DSS requirement, handled by payment processor |
| Real-time dashboard | CloudWatch sufficient for demo | Would add Grafana or QuickSight |

Being explicit about scope boundaries is part of architectural maturity. Knowing what you're not building — and why — is as important as what you are.

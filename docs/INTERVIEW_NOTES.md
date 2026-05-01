# Interview Notes — How to Talk About This Project

This document is for you. It maps each technical component to a talking point grounded in your production experience. The goal is not to memorize answers — it's to connect cloud concepts to things you've already lived.

---

## The Opening Frame

When asked "tell me about this project," don't start with tech. Start with the problem:

> "I've spent 14 years building and operating fraud prevention infrastructure in production — 500 TPS, sub-second SLAs, mainframe-to-distributed migrations. What I wanted to validate was whether I could design that same class of system from scratch on cloud-native AWS infrastructure, making every architectural decision explicit and defensible. FraudShield is that validation."

This reframes the conversation: you're not a developer showing a side project. You're a senior technical lead who built something to close a specific gap.

---

## Component-by-Component Talking Points

### API Gateway
**If asked:** "Why API Gateway instead of a load balancer in front of EC2?"

> "For a fraud scoring endpoint, the traffic pattern is bursty and unpredictable — that's exactly the nature of card transaction volume. API Gateway + Lambda scales to zero and to thousands concurrently without pre-provisioning. With EC2 behind a load balancer, I'd be paying for capacity that sits idle 80% of the time and scrambling to scale during peak. The latency profile is also better for Lambda at p99 than a warm EC2 under burst — which matters when your SLA is 1.6 seconds."

This answer connects cloud concepts to your lived experience with burst transaction volume.

---

### SQS Decoupling
**If asked:** "Why not call the processor Lambda directly from the scorer?"

> "Synchronous chaining creates a failure cascade. If the processor is slow — say DynamoDB has a write latency spike — that latency propagates back to the scorer, which propagates back to the client. Now you've blown the SLA because of a persistence layer issue that has nothing to do with the fraud decision. SQS absorbs that. The client gets a response the moment the fraud decision is made. The persistence is guaranteed by queue durability, not by blocking the client. This is the same pattern we used to isolate the fraud engine from downstream systems in Actimize — the decision layer and the recording layer operate independently."

---

### Terraform
**If asked:** "Why Terraform instead of the AWS console or CloudFormation?"

> "Three reasons. First, reproducibility — I can destroy and recreate the entire environment in minutes with the same configuration. Second, version control — every infrastructure change is a Git commit with a diff, which means full audit trail. Third, portability — if this were a real client engagement and they used GCP or Azure for part of their stack, Terraform handles it without relearning a new tool. CloudFormation is AWS-only. In an enterprise consulting context like Xal Digital, that matters."

---

### Fraud Scoring Rules
**If asked:** "How did you decide on these scoring rules?"

> "The rule weights reflect real fraud pattern priorities from production. Velocity carries the most weight because card testing attacks — where fraudsters validate stolen cards with rapid sequential transactions — are detectable through velocity before the amounts are large enough to trigger amount-based rules. We caught this pattern in production before it escalated. The amount rule uses a multiplier against historical average rather than a fixed threshold, because a $500 transaction is normal for one cardholder and anomalous for another. Geo risk is the weakest signal alone but amplifies the others — high velocity from a high-risk country is a near-certain decline."

---

### CI/CD Pipeline
**If asked:** "Walk me through your CI/CD setup."

> "Every push to main triggers a four-stage pipeline: test, lint, terraform plan, then apply. The plan stage is key — it outputs exactly what will change in AWS infrastructure before anything is deployed. No surprises. This is the governance pattern I implemented for Python ETL delivery at Banamex, where we went from 8-week to 4-week delivery cycles by automating the validation gates that were previously manual and sequential. The principle is the same: you compress cycle time by parallelizing what can be parallelized and eliminating human handoffs between stages that can be codified."

---

### IAM Design
**If asked:** "How did you handle permissions?"

> "Each Lambda has its own role with only the permissions it needs for its specific job. The scorer can read DynamoDB and write to SQS. The processor can read from SQS and write to DynamoDB. Neither has admin access, neither has access to the other's resources. In a regulated banking environment, wildcard IAM permissions are a compliance finding — that's not hypothetical, I've seen it surfaced in regulatory audits. Least privilege is not best practice here, it's a requirement."

---

## Toku TAM-Specific Angle

For Toku, the conversation is about integration reliability, not fraud domain:

> "The architecture pattern here — API Gateway as entry point, async decoupling via SQS, structured logging in CloudWatch — is exactly the integration reliability stack I'd design for a client onboarding flow at Toku. The domain changes (payments vs. payroll), but the resilience principles are identical: decouple decision from persistence, make every failure observable, design for retry without side effects."

Key Toku terms to use naturally: **idempotency**, **retry logic**, **observability**, **webhook reliability**, **integration handoff**.

---

## Xal Digital-Specific Angle

For Xal, the conversation is about architectural leadership:

> "This project was my way of validating that I can operate at the infrastructure level, not just the application layer. I made every architectural decision — the component selection, the IAM model, the CI/CD gates, the DynamoDB table design — and I can defend each one against alternatives. That's the mode I'd operate in as Technical Manager: not coding every component, but owning the architectural decisions and being the person the team brings hard trade-offs to."

Key Xal terms: **Well-Architected Framework**, **operational excellence**, **security pillar**, **cost optimization**, **trade-off analysis**.

---

## Questions to Ask Them (signals technical depth)

- "How does your current CI/CD pipeline handle infrastructure changes versus application code changes — are they in the same pipeline or separated?"
- "What's your current observability stack — are you using CloudWatch natively or have you layered something like Datadog or Grafana on top?"
- "When you talk about integration reliability, what does your SLA look like end-to-end for a client onboarding flow?"
- "How do you handle schema changes in DynamoDB across environments — do you version your table definitions in Terraform?"

These questions signal that you think in systems, not features.

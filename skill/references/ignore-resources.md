# Resources to Ignore

When generating an architecture diagram, the following resources should **not** appear as visible nodes. They are infrastructure/security concerns that would clutter the diagram without adding architectural value.

## Ignored Resources

| Resource | Reason |
|----------|--------|
| KMS (Key Management Service) | Encryption at rest — implied, not architectural |
| SQS DLQ (Dead Letter Queue) | Error-handling infra — only ignore DLQs, not primary SQS queues |
| IAM Role | Security/permission boundary — implied by every service interaction |
| IAM Policy | Same as above |
| Security Group | Network-level — not architectural flow |
| CloudWatch Log Group | Observability — implied, not architectural |
| CloudWatch Alarm | Same as above |
| SNS Topic (internal/DLQ alarm) | Only ignore alarm/notification topics, not business SNS topics |

## Rule

If a resource exists solely for security, encryption, error-handling, or observability,
it should be **omitted** from the diagram. Only resources that participate in the
**business logic / data flow** should be rendered as nodes.

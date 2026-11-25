# Resources to Ignore

When generating an architecture diagram, the following resources should **not** appear as visible nodes. They are infrastructure/security concerns that would clutter the diagram without adding architectural value.

## Ignored Resources

| Resource | Reason |
|----------|--------|
| KMS (Key Management Service) | Encryption at rest — implied, not architectural |
| SQS DLQ (Dead Letter Queue) | Error-handling infra — only ignore DLQs, not primary SQS queues |
| SQS failure/redrive queue | Same as above |
| IAM Role | Security/permission boundary — implied by every service interaction |
| IAM Policy | Same as above |
| Security Group | Network-level — not architectural flow |
| CloudWatch Log Group | Observability — implied, not architectural |
| CloudWatch Alarm | Same as above |
| SNS Topic (alert/notification) | Only ignore alerting topics (e.g. `inventory_alerts`), not business SNS topics (e.g. `availability_sent`) |
| Test scaffolding (`smoke_`) | Test-only resources — not part of the runtime data flow |

Enforced in `scripts/render.py` via `DLQ_MARKERS` (`_dlq`, `_failures`, `_alerts`,
`_alarm`, `notification`, `smoke_`) plus the entries above, and applied
both at discovery and as a render-time prune so a hand-authored model cannot
reintroduce these nodes.

## Rule

If a resource exists solely for security, encryption, error-handling, or observability,
it should be **omitted** from the diagram. Only resources that participate in the
**business logic / data flow** should be rendered as nodes.

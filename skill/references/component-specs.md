# Component Reference

**Layout, geometry, color, and XML rules are computed by `scripts/render.py`.**
This file only documents the service → icon/color mapping for humans.

## AWS Service resIcon Reference

| Service | `resIcon` / shape | fillColor |
|---------|-------------------|-----------|
| SQS | `mxgraph.aws4.sqs` | `#E7157B` |
| SNS | `mxgraph.aws4.sns` | `#E7157B` |
| EventBridge | `mxgraph.aws4.eventbridge` | `#E7157B` |
| Kinesis | `mxgraph.aws4.kinesis` | `#E7157B` |
| CloudWatch | `mxgraph.aws4.cloudwatch` | `#E7157B` |
| Step Functions | `mxgraph.aws4.step_functions` | `#ED7100` |
| Lambda | `mxgraph.aws4.lambda` | `#ED7100` |
| ECS | `mxgraph.aws4.ecs` | `#ED7100` |
| EKS | `mxgraph.aws4.eks` | `#ED7100` |
| SageMaker | `mxgraph.aws4.sagemaker` | `#ED7100` |
| Bedrock | `mxgraph.aws4.bedrock` | `#ED7100` |
| DynamoDB | `mxgraph.aws4.dynamodb_standard_access_table_class` | `#C925D1` |
| API Gateway | `mxgraph.aws4.api_gateway` | `#C925D1` |
| Aurora | `mxgraph.aws4.aurora` | `#C925D1` |
| RDS | `mxgraph.aws4.rds` | `#C925D1` |
| Cognito | `mxgraph.aws4.cognito` | `#C925D1` |
| CloudFront | `mxgraph.aws4.cloudfront` | `#C925D1` |
| Route 53 | `mxgraph.aws4.route_53` | `#C925D1` |
| Secrets Manager | `mxgraph.aws4.secrets_manager` | `#C925D1` |
| S3 | `mxgraph.aws4.s3` | `#7AA116` |
| VPC | `mxgraph.aws4.vpc` | `#7AA116` |
| IAM | `mxgraph.aws4.iam` | `#232F3E` |

## Color Categories

| Category | Hex | Services |
|----------|-----|----------|
| Compute | `#ED7100` | Lambda, Step Functions, ECS, EKS, SageMaker, Bedrock |
| Messaging / Integration | `#E7157B` | SQS, SNS, EventBridge, Kinesis, CloudWatch |
| Database / Storage | `#C925D1` | DynamoDB, RDS, Aurora, API Gateway, Cognito, CloudFront, Route 53 |
| Networking / Content | `#7AA116` | S3, VPC |
| Security | `#232F3E` | IAM |

## Geometry

| Property | Value |
|----------|-------|
| Icon size | 80 × 80 |
| External box width | 160 |
| External box height | span of connected nodes + 120 |

All placement, spacing, waypoint, and external-box sizing rules are implemented
in `scripts/render.py` — see that file for the canonical values.

## External box labels

External boxes follow the same naming convention as the AWS nodes: a bold
snake_case resource `name` (e.g. `almere_consignment_cancel_queue`, like
`tam_cancel`) — never friendly prose such as "Almere Order System".

The second line shows the resource type, derived from the id suffix by
`scripts/render.py` (`_queue` → `SQS`, `_topic` → `SNS`, otherwise omitted),
mirroring how the AWS nodes display their type (Lambda, SQS, SNS, DynamoDB).
Set the model's `description` only to describe a non-queue/topic external (e.g.
an on-prem TCP endpoint).

`scripts/render.py` warns when an external `name` contains spaces/hyphens or
uppercase letters (prose), and when a `description` exceeds 24 characters.

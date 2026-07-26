# Component Specifications

Extracted from `aws_arch_template.drawio`.

## AWS Resource Icons

### Base Style String

```
sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;
```

### Per-Service Additions

| Service | `resIcon` | `fillColor` |
|---------|-----------|--------------|
| SQS | `mxgraph.aws4.sqs` | `#E7157B` |
| SNS | `mxgraph.aws4.sns` | `#E7157B` |
| EventBridge | `mxgraph.aws4.eventbridge` | `#E7157B` |
| Lambda | `mxgraph.aws4.lambda` | `#ED7100` |
| DynamoDB | `mxgraph.aws4.dynamodb` | `#C925D1` |

### Geometry

| Property | Value |
|----------|-------|
| Width | `80` |
| Height | `80` |
| Aspect | `aspect=fixed` |

### Label

| Property | Value |
|----------|-------|
| Position | Below icon (`verticalLabelPosition=bottom;verticalAlign=top`) |
| Alignment | `align=center` |

#### Label Value Encoding (CRITICAL)

Labels use HTML inside the `value` attribute. The HTML tags must be XML-escaped ONCE.

**Rule:** Take the desired HTML, then XML-escape `<` → `&lt;` and `>` → `&gt;`. Do NOT double-escape.

```
Desired rendering:  <b>order_ingest</b><div>SQS</div>
XML value:          &lt;b&gt;order_ingest&lt;/b&gt;&lt;div&gt;SQS&lt;/div&gt;
```

**Wrong (double-escaped — renders as literal `&lt;b&gt;` text):**
```
&amp;lt;b&amp;gt;order_ingest&amp;lt;/b&amp;gt;  ← NEVER DO THIS
```

**For plain text labels (no bold/formatting),** just text with `<div>` for line breaks:
```
XML value:  order_ingest&lt;div&gt;SQS
```

**External box labels** follow the same rule:
```
Desired rendering:  <b>WMS</b><div>Warehouse Management</div>
XML value:          &lt;b&gt;WMS&lt;/b&gt;&lt;div&gt;Warehouse Management&lt;/div&gt;
```

---

## External Resource Boxes

### Style String

```
rounded=1;whiteSpace=wrap;html=1;
```

- **No** `aws4` shape — these are NOT AWS resources
- No explicit fill color (defaults to light gray)

### Geometry

| Property | Value |
|----------|-------|
| Width | `160` (always) |
| Height | Variable — `160` for 1 row, `480` for 3 rows, etc. |
| Left position | `x=-80` |
| Right position | `x=1920` |

### Value Format

```
&amp;lt;external&amp;gt;<div>Name</div>
```

### Height Matching Rule

An external box must have its height match the vertical span of the rows it connects to:

```
height = (connected_row_count × 320) - 160 + (extra_for_last_row)
```

For a 1-row external: `h=160`
For a 3-row external (spanning rows at y=160, 480, 800): `h=480`

---

## Title Bar

| Property | Value |
|----------|-------|
| Style | `text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=18;fontStyle=1;fontColor=#232F3E;strokeWidth=1;` |
| Position | `x=0, y=0` |
| Size | `width=1700, height=40` |
| Value | `<font style="font-size: 24px;">&lt;TITLE&gt;</font>` |

---

## Complete AWS Service resIcon Reference

For the skill to generate arbitrary diagrams, here is the full mapping of common AWS services to their `mxgraph.aws4.*` identifiers and colors:

| Service | resIcon | fillColor |
|---------|---------|-----------|
| SQS | `mxgraph.aws4.sqs` | `#E7157B` |
| SNS | `mxgraph.aws4.sns` | `#E7157B` |
| EventBridge | `mxgraph.aws4.eventbridge` | `#E7157B` |
| Step Functions | `mxgraph.aws4.step_functions` | `#ED7100` |
| Lambda | `mxgraph.aws4.lambda` | `#ED7100` |
| DynamoDB | `mxgraph.aws4.dynamodb` | `#C925D1` |
| API Gateway | `mxgraph.aws4.api_gateway` | `#C925D1` |
| S3 | `mxgraph.aws4.s3` | `#7AA116` |
| Kinesis | `mxgraph.aws4.kinesis` | `#E7157B` |
| CloudWatch | `mxgraph.aws4.cloudwatch` | `#E7157B` |
| ECS | `mxgraph.aws4.ecs` | `#ED7100` |
| EKS | `mxgraph.aws4.eks` | `#ED7100` |
| Aurora | `mxgraph.aws4.aurora` | `#C925D1` |
| RDS | `mxgraph.aws4.rds` | `#C925D1` |
| Sagemaker | `mxgraph.aws4.sagemaker` | `#ED7100` |
| Bedrock | `mxgraph.aws4.bedrock` | `#ED7100` |
| Cognito | `mxgraph.aws4.cognito` | `#C925D1` |
| CloudFront | `mxgraph.aws4.cloudfront` | `#C925D1` |
| Route 53 | `mxgraph.aws4.route_53` | `#C925D1` |
| VPC / Subnet | `mxgraph.aws4.vpc` | `#7AA116` |
| IAM | `mxgraph.aws4.iam` | `#232F3E` |
| Secrets Manager | `mxgraph.aws4.secrets_manager` | `#C925D1` |
| SQS | `mxgraph.aws4.sqs` | `#E7157B` |
| SNS | `mxgraph.aws4.sns` | `#E7157B` |

### Color Category Rules

| Category | Color | Hex |
|----------|-------|-----|
| Compute | Orange | `#ED7100` |
| Messaging / Integration | Pink | `#E7157B` |
| Database / Storage | Purple | `#C925D1` |
| Networking / Content | Green | `#7AA116` |
| Security / Identity | Dark navy | `#232F3E` |

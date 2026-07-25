# Color Rules

Extracted from `aws_arch_template.drawio`.

## AWS Service Fill Colors

| Color | Hex | Role | Services |
|-------|-----|------|----------|
| Pink | `#E7157B` | **Messaging / Integration** | SQS, SNS, EventBridge |
| Orange | `#ED7100` | **Compute** (neutral) | Lambda |
| Purple | `#C925D1` | **Database / Storage** | DynamoDB |

## Arrow Color Rule (CRITICAL)

```
Arrow strokeColor = fillColor of the NON-LAMBDA service in the connection.
Lambda's orange (#ED7100) is NEVER used as an arrow color.
```

### Decision logic:

```
if source is External:
    → no strokeColor (default black/gray)

elif one side is Lambda:
    → use the OTHER service's fill color

elif neither side is Lambda:
    → use the SOURCE service's fill color
```

### Evidence from template:

| Edge | Arrow Color | Why |
|------|-------------|-----|
| SQS → Lambda | `#E7157B` (SQS pink) | Lambda neutral → SQS color wins |
| Lambda → DynamoDB | `#C925D1` (DDB purple) | Lambda neutral → DDB color wins |
| Lambda → SNS | `#E7157B` (SNS pink) | Lambda neutral → SNS color wins |
| DynamoDB → Lambda | `#C925D1` (DDB purple) | Lambda neutral → DDB color wins |
| Lambda → SQS | `#E7157B` (SQS pink) | Lambda neutral → SQS color wins |
| SNS → External | `#E7157B` (SNS pink) | Source = SNS |
| EventBridge → Lambda | `#E7157B` (EB pink) | Lambda neutral → EB color wins |
| External → SQS | _(none, default)_ | Source is External |

## Stroke Color Format

Use `light-dark()` CSS function for dark/light mode support:

```
strokeColor=light-dark(#e7167b, #ededed)
strokeColor=light-dark(#c924d0, #ededed)
```

- First argument: the AWS service color (lowercase hex)
- Second argument: `#ededed` (light gray for dark mode)

## Text Colors

| Element | Color |
|---------|-------|
| Icon labels | `#232F3E` |
| Title | `#232F3E` |
| External box labels | `#232F3E` (default) |

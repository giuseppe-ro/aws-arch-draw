# Graphify Discovery Strategy

The skill discovers architecture ONLY via graphify queries against an existing `graphify-out/graph.json`.
Never read project source files. Never hardcode service names.

## Query Approach

Run queries in order. Merge results. If any query is truncated (`X of Y nodes`), raise `--budget`
or split the query before continuing — truncated output discards data.

### Phase A — Resource Inventory

Get a broad inventory of all AWS resources in the project:

```
graphify query "list all AWS services and resources in this project. For each one, give its type (Lambda, SQS, SNS, DynamoDB, EventBridge, API Gateway, S3, Kinesis, Step Functions, ECS, etc) and its purpose." --budget 8000
```

Parse the output to build a list of `{name, type, purpose}` entries.

**Filter:** Remove any resource whose type matches an entry in `references/ignore-resources.txt`
(case-insensitive match against the type name. e.g. "kms" removes all KMS resources,
"sqs dlq" removes dead-letter queues but NOT primary SQS queues).

**Stop condition:** If zero supported AWS resources remain after filtering, stop and tell the user.

### Phase B — Connection Discovery

For each remaining resource, trace its connections:

```
graphify query "what does <resource_name> call or send data to? What calls or sends data to <resource_name>? List all upstream and downstream connections." --dfs --budget 4000
```

Run this per unique resource. Merge all results to build a directed graph of connections.

### Phase C — External Systems

Find non-AWS external systems:

```
graphify query "what external systems, third-party services, user interfaces, or non-AWS endpoints does this project interact with?" --budget 4000
```

External systems become the left/right boundary boxes in the diagram.

## Building the Architecture Model

From merged query results, build:

1. **Nodes:** each unique AWS resource (name + type)
2. **Edges:** each connection between resources (source → target, with direction)
3. **External sources:** systems that feed data IN (go on left)
4. **External sinks:** systems that receive data OUT (go on right)

## Layout Assignment

Using the connection graph:

1. **Left → Right flow:** Sources at the left, compute in middle, databases/storage at right
2. **Row assignment:** Each independent flow chain gets its own row
3. **External placement:** Upstream externals at `x=-80`, downstream at `x=1920`
4. **Shared resources:** A DynamoDB table or SQS queue used by multiple flows appears ONCE,
   positioned between the rows that use it, with distributed entry points

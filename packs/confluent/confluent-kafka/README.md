# Pack `confluent-kafka` — Kafka and Flink by Confluent

Vendor: `confluent` (an IBM company since March 2026). Curated from [confluentinc/agent-skills](https://github.com/confluentinc/agent-skills) (Apache-2.0) at commit `914d95eff7ff`. Install with `uvx bob-skills add confluent-kafka`, or with `/skills-add confluent-kafka` inside Bob once bob-essentials is installed.

## Before you install

**The Confluent Cloud skills create and delete environments, connectors, topics and Flink statements, and Flink statements consume CFUs while they run.**

Covered by: The skills present a plan and run EXPLAIN before CREATE; the security-defaults rule adds a yes per create or delete, named by object and environment. The teardown script asks once before it deletes the demo topics and local state.

**The bundled docker-compose files publish the broker, REST proxy and Schema Registry without authentication on every network interface, and the setup guides write cluster keys into local properties files.**

Covered by: Publish those ports as `127.0.0.1:PORT:PORT` when you run them, and add the key files to `.gitignore` as the Java skill does.

| Skill | What it adds |
|---|---|
| `developing-kafka-java-client` | Java producer and consumer projects on the Apache Kafka clients with Avro, JSON Schema or Protobuf through Schema Registry; Maven or Gradle |
| `developing-kafka-python-client` | Python producer and consumer projects on confluent-kafka-python with Schema Registry, sync or async, with mocked unit tests |
| `kafka-streams-programming` | Design, build and debug Kafka Streams topologies; helper scripts create topics, produce test data, verify output and tear down |
| `kafka-schema-registry` | Scan a repository for Kafka producers and consumers, extract schemas, tag PII fields, generate Terraform for Schema Registry and a rollout report |
| `flink-udf` | Java scalar, table and process table functions for Flink SQL and the Table API |
| `confluent-cloud-flink-sql` | Flink SQL that runs on Confluent Cloud, with the Confluent Cloud versus Apache Flink dialect traps and `EXPLAIN` before `CREATE` |
| `confluent-cloud-cdc-tableflow` | CDC from SQL Server, MySQL, PostgreSQL, Oracle or DynamoDB through Debezium and Flink into Iceberg or Delta tables with Tableflow |
| `msk-migration` | Assess and plan a move from AWS MSK to Confluent Cloud with KCP scans, sizing and a switchover plan |

## Before you use it

- The Confluent Cloud skills need the `confluent` CLI with a logged-in session. Flink statements consume CFUs: `confluent-cloud-flink-sql` runs `EXPLAIN` before `CREATE`, and both Confluent Cloud skills present a plan and wait for confirmation before they create connectors, statements or compute pools.
- The client skills work against Confluent Cloud, a local Docker broker or WarpStream. IBM Event Streams is Kafka-compatible, but these templates are written for Confluent endpoints.
- `confluent-cloud-cdc-tableflow` prefers the Confluent MCP server and falls back to the CLI and REST API without it. This pack does not install the server yet: a pinned version with telemetry off and delete tools blocked is planned for 1.1.
- Each skill ships the `evals/` Confluent scores it against, including mock repositories that `kafka-schema-registry` reads as sample input.

Not included: `confluent-skill-creator` and `confluent-skill-reviewer`, which serve contributors to the upstream repository.

Refresh with `python3 scripts/sync_upstream.py confluent-kafka`, then `bob-skills registry validate --fix`, lint, scanners, version bump, PR, tag.

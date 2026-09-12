# IBM security MCP servers: review notes

Reviewed on 2026-09-11 for a possible `security-ops` pack: code and documentation of five servers. None of them can back a marketplace pack today, so `security-ops` will be written as our own read-only skills.

| Server | Reviewed at | Licence | Maintenance | What the agent can do by default | Verdict |
|---|---|---|---|---|---|
| QRadar, [IBM/qradar-mcp](https://github.com/IBM/qradar-mcp) | `c4742b6f4747` | Apache-2.0 | 13 commits, 11 by one author; the README says it is not an IBM product and will not be maintained | 83 tools: close and assign offenses, create and delete reference data, deploy configuration, manage users | Not as is |
| Guardium Data Protection, [IBM/gdp-mcp-server](https://github.com/IBM/gdp-mcp-server) | `2e174b1e6b9a` | none | 4 commits, 1 author | Any of 579 REST endpoints, Guard CLI over SSH | Blocked: no licence |
| Guardium Cryptography Manager, [IBM/gcm-mcp-server](https://github.com/IBM/gcm-mcp-server) | `a2e08f7c47e4` | none | 4 commits | Raw calls to the whole API | Blocked: no licence |
| OpenPages, [IBM/ibm-openpages-mcp-server](https://github.com/IBM/ibm-openpages-mcp-server) | `3bf3fda19d60` | badge only | 8 commits; the Apache-2.0 local server is archived | GRC objects over HTTP or stdio | Ask the OpenPages team |
| Verify, [docs.verify.ibm.com](https://docs.verify.ibm.com/verify/docs/verify-mcp-server) | documentation | not stated | Container you deploy yourself | 34 tools: create and delete users, groups and applications, reset passwords, delete MFA enrolments | Later, read-only |

## Remarks

**QRadar**

1. Write tools are on by default. `feature_toggles.json` enables GET, POST, PUT and DELETE for every group, and the file is read from the package folder with no environment override, so a read-only deployment means editing the installed package.
2. Local mode listens on every interface: `server.py` line 366 runs uvicorn on `0.0.0.0:5000`, while `config.example.json` suggests `127.0.0.1`.
3. Local mode fills in the configured token when a request carries none: the REST client takes tokens from the request headers and falls back to `config.json`. Together with remark 2, anyone who reaches port 5000 acts with the analyst's token.
4. TLS verification is off unless configured: `verify_ssl` defaults to false in local mode, and app mode keeps it off until `REQUESTS_CA_BUNDLE` is set.
5. Tokens sit in plain text in `config.json`, and the example config enables debug.
6. SIEM data is written by the attacker. Offense descriptions and event payloads reach the model; with write tools on, an instruction planted in an event can close the offense or remove an IP from a blocking reference set.
7. Worth keeping: the audit log redacts token fields, and the AQL field, function and query-guide resources are useful.

**Guardium Data Protection**

1. No LICENSE file, although the README refers to "the associated open source software license".
2. `gdp_execute_api` calls any endpoint and `gdp_guard_cli` runs appliance commands over SSH. Destructive commands ask for confirmation through MCP elicitation, which depends on the client supporting it.
3. Worth keeping: credentials in a keystore file with mode 600.

**Guardium Cryptography Manager**

1. No LICENSE file; one raw API tool exposes the whole API.

**OpenPages**

1. The README shows an Apache-2.0 badge and points the licence link at CONTRIBUTING.md; the repository has no LICENSE file.

**Verify**

1. Full user, group and application administration plus password resets and MFA deletion, with no licence stated.
2. Worth keeping: OAuth 2.0 token exchange, so the user signs in with Verify instead of pasting a key.

## What a server needs before a pack can reference it

- A licence file that allows use and redistribution: Apache-2.0, MIT or MPL-2.0.
- Read-only by default; writes enabled per tool through an allow-list or a read-only switch in a flag or environment variable.
- Stdio or a listener on 127.0.0.1, and no stored-credential fallback for requests without their own.
- TLS verification on by default; secrets from the environment, not from config files.
- A released, pinnable version and an owner who answers security reports.

The client-side part is enforced for every pack: `mcpServers` entries pass checks M001–M007 and declare `mcpAccess` ([security-gate.md](../security-gate.md)).

## What we build instead

`security-ops`, our own pack: `qradar-investigation` with a small read-only client script (TLS on, token from the environment, no write endpoint in the code), a rule that SIEM content is data, `incident-report`, and `compliance-evidence` built on appsec-dev results. The whole integration then goes through our gate, which MCP servers do not. Release only after a run against a live QRadar instance. Guardium, Verify and OpenPages follow once their servers meet the list above.

# Authentication

The client reads credentials from the environment only and mints the token in memory. It never reads `~/.cache/orchestrate/credentials.yaml` or `~/.config/orchestrate/config.yaml`: the ADK CLI caches tokens there, and agentops' `tenant_setup` rewrites both files on every run.

Evidence markers are the same as in `api-routes.md`: **confirmed-in-code**, **spec-only**, **unverified**. Nothing was observed on a live instance.

## Variables

| Variable | Meaning |
|---|---|
| `WO_INSTANCE` | Instance URL. `https://` always; `http://` only for `localhost`, `127.0.0.1` or `[::1]`. No user or password inside the URL |
| `WO_API_KEY` | API key; exchanged for a bearer token at an IBM token service, only for an instance on an IBM host (`*.ibm.com`) |
| `WO_TOKEN` | A bearer token the user minted; used as it is and never re-minted |
| `WO_AUTH_TYPE` | Optional: `ibm_iam` (alias `iam`), `mcsp`, `mcsp_v1`, `mcsp_v2`, `local`, `token`. `cpd` is refused: use `WO_TOKEN` |
| `WO_IAM_URL` | Optional base URL of the token service, for a private or regional one. It must be on an IBM host (`*.ibm.com`): the key goes there |
| `WO_CA_BUNDLE` | Optional PEM file of a private certificate authority |
| `WO_USERNAME`, `WO_PASSWORD` | Developer Edition only, when `WO_TOKEN` is not set |

The user exports them in their own shell. Never ask for a key or password in the chat, never pass one on a command line, and never write one to a project file. Bob never sets a `WO_*` variable, not even inline on a command.

Developer Edition: `WO_INSTANCE=http://localhost:4321`, with `WO_TOKEN`, or `WO_USERNAME` and `WO_PASSWORD`. `WO_API_KEY` does not apply there. The `WO_INSTANCE` and `WO_API_KEY` in the ADK server's `.env` name the SaaS tenant it pulls images and models from, not the local server: exported into the shell as they are, they point the client at SaaS. The plan and the dry run print the host before anything is sent; check it.

## First setup

1. Find the values. SaaS: open the watsonx Orchestrate instance, then Settings, then API details. It shows the instance URL (`WO_INSTANCE`) and lets the user generate an API key (`WO_API_KEY`). Developer Edition: `http://localhost:4321` and the local login.
2. The user exports them in the shell that Bob's terminal starts from, for example in the shell profile, and reopens that terminal:

   ```bash
   export WO_INSTANCE="<instance URL from Settings, API details>"   # IBM Cloud: https://api.<region>.watson-orchestrate.cloud.ibm.com/instances/<id>
   export WO_API_KEY="<the key>"
   ```

   Never paste a key into the chat. Bob never writes it to a file.
3. Check without printing a secret: `python3 <wxo-agent-api skill>/scripts/wxo_client.py agents`. It only reads. A missing variable stops it before any request with a message that names the variable and no value; on success it prints the auth path and the agents.

## How the client picks a path

First match wins; `client.auth_path` and the probe's `auth_path` record the path that worked.

1. `WO_AUTH_TYPE=token`, or `WO_TOKEN` set without `WO_AUTH_TYPE`: the token as given. `WO_TOKEN` wins over `WO_API_KEY`.
2. An instance URL that starts with `https://cpd` (the ADK's rule for Cloud Pak for Data): `WO_TOKEN`, else an error. The key never goes to an IBM SaaS token service.
3. A local host, or `WO_AUTH_TYPE=local`: `WO_TOKEN`, else the Developer Edition login.
4. No API key: `WO_TOKEN`, else an error.
   An API key with an instance whose host does not end in `.ibm.com`: an error. The key and the token minted from it stay with IBM hosts; for any other host, mint a token and set `WO_TOKEN`.
5. `WO_AUTH_TYPE=ibm_iam`, or a host ending in `.cloud.ibm.com` with no `WO_AUTH_TYPE`: IBM Cloud IAM.
6. `WO_AUTH_TYPE=mcsp_v1`: MCSP v1. `WO_AUTH_TYPE=mcsp_v2`: MCSP v2 scopeless, then scoped.
7. `WO_AUTH_TYPE=mcsp`: MCSP by the key's prefix, as in rule 8, even on a `cloud.ibm.com` host.
8. By the key's prefix (strict base64 decode): `k1:` gives MCSP v1; `k2:` gives v2 scopeless, then scoped; any other key gives MCSP v1, then v2 scopeless, then v2 scoped.

The scoped v2 path needs `/instances/<id>` in `WO_INSTANCE`.

## Token services

### IBM Cloud IAM (hosts under `cloud.ibm.com`)
- **confirmed-in-code** (the IBM Cloud SDK authenticator the ADK uses).
- `POST https://iam.cloud.ibm.com/identity/token`, form-encoded `grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=<key>`. The token is in `access_token`.

### MCSP v1 (AWS-hosted SaaS)
- **confirmed-in-code** (ADK).
- `POST https://iam.platform.saas.ibm.com/siusermgr/api/1.0/apikeys/token` with JSON `{"apikey": "<key>"}`. The token is in `token`.

### MCSP v2
- **confirmed-in-code**, two variants:
  - Scoped, ADK 2.1.0: `POST https://account-iam.platform.saas.ibm.com/api/2.0/services/<instance id>/apikeys/token`.
  - Scopeless, ADK 2.17: `POST https://account-iam.platform.saas.ibm.com/api/2.0/apikeys/token?includeBuiltinActions=false&includeCustomActions=false&includeRoles=true&prefixRolesWithDefinitionScope=false`.
- Both take JSON `{"apikey": "<key>"}` and return the token in `token`.
- Instances in `germanywestcentral` use the regional host `https://account-iam.azure.westus3.platform.saas.ibm.com`. `WO_IAM_URL` overrides the base.
- Which variant a given tenant accepts is **unverified**. The client tries them in order and reports each failure without the key.

### Developer Edition (`http://localhost:4321`)
- **confirmed-in-code** (ADK local login) and in the developer docs.
- `POST {instance}/api/v1/auth/token`, form `username`, `password`: a global token.
- `GET {instance}/api/v1/tenants` with it; the client picks the tenant named `wxo-dev`, or the only tenant.
- `POST {instance}/api/v1/auth/token?tenant_id=<id>` with the same form: the tenant token. It may carry no expiry; the client then refreshes it only on a 401.
- The client never creates a tenant. It never uses the default local credentials built into the ADK: the user sets `WO_USERNAME` and `WO_PASSWORD`, or `WO_TOKEN`.

### CPD and on-prem
- **unverified**. IBM sources disagree: the ADK uses the CPD authenticator (`/icp4d-api`), while the Hub getting-started page sends the Zen API key directly.
- The client does not guess. The user mints a bearer token by their own procedure and exports `WO_TOKEN`.

## Token lifetime

- A minted token is refreshed 600 s before its `exp` (or halfway through a lifetime shorter than 20 minutes), as the ADK does.
- On a 401 the client mints once more and repeats the request. A second 401 is an error.
- `WO_TOKEN` is never re-minted. An expired `WO_TOKEN` stops the client before it sends anything; a 401 on it is final.

## Transport

- TLS verification is always on. A private CA goes in `WO_CA_BUNDLE`; it becomes the trust store of the default context. A certificate error stops the task; it is not something to work around.
- Redirects are never followed, so the `Authorization` header cannot travel to another host. `client.request()` refuses any URL outside the scheme, host and port of `WO_INSTANCE` before it takes a token.
- Requests to `localhost`, `127.0.0.1` or `::1` never go through a proxy from `http_proxy` or `https_proxy`: plain http would hand the token, the prompts and the tool results to it. Remote hosts use the environment's proxy, through a TLS tunnel.
- Every request has a timeout and a size cap. The timeout bounds each wait for data, and a body's deadline is checked between reads, so a server that sends a byte now and then can hold one read longer. The client sends GET and POST only.

## Keeping the token secret

- The token lives in the client object. It is never returned, printed, logged or written.
- Error messages pass through a redactor that removes the key, the token, the password, any `Bearer` value and any JWT-shaped string. Scripts print errors as the client raises them.
- A `WO_TOKEN` or `WO_API_KEY` with whitespace or a line break (a wrapped paste), or a `WO_PASSWORD` with a line break, is refused before any request. The message names the variable, never the value.
- The evaluation framework (`agentops`) behaves differently: `tenant_setup` rewrites both orchestrate config files, an expired token opens a password prompt, and TLS verification is off unless `WO_SSL_VERIFY=true` is set. The pack never imports it.

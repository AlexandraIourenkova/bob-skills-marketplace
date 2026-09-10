# watsonx Orchestrate: bundling SQLite inside a Python tool

## The mechanism (verified against ADK source, Aug 2026)

`orchestrate tools import -k python` with `--package-root/-p` uploads **every file**
in the package directory (zipped as `artifacts.zip`) — including binary data files
like a SQLite `.db`. At runtime the files sit next to the tool module, so
`Path(__file__).parent / "data.db"` resolves correctly. This shipped in ADK 1.x
(multi-file Python tool support, April 2025); any current ADK version has it.

```bash
orchestrate tools import -k python \
    -f tool_pkg/query_mydata.py \
    -p tool_pkg \
    -r tool_pkg/requirements.txt
```

Rules and limits:

- **50 MB max** for the compressed tool bundle (SQLite files compress well —
  roughly 5–10× — so ~200–300 MB raw DB is the practical ceiling; check the
  actual zip size if in doubt: `zip -r /tmp/test.zip tool_pkg && ls -lh /tmp/test.zip`).
- `-p` and `-f` must share a common base path; **file and folder names inside the
  package: alphanumeric + underscores only** (no hyphens).
- `requirements.txt` inside the package is excluded from the artifact and handled
  separately; the ADK appends `ibm-watsonx-orchestrate==<version>` itself.
- Only `@tool`-decorated functions in the `-f` entry file become tools; other
  files are helpers/data.
- The **tool runtime filesystem is read-only**. Open SQLite with
  `sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)` so it never
  tries to create journal/WAL files. `sqlite3` is stdlib — no requirements entry.
- Re-importing a tool with the same name **updates** it — that is how you refresh
  the data: rebuild `data.db`, re-run the same `tools import` command.

Docs: https://developer.watson-orchestrate.ibm.com/tools/create_tool

## ADK installation gotcha

The ADK CLI is fragile about dependency versions (pydantic/urllib3 conflicts in a
shared Python make `orchestrate` crash on startup with a pydantic schema
traceback). Always use a dedicated venv:

```bash
python3.12 -m venv ~/.venvs/wxo && source ~/.venvs/wxo/bin/activate
pip install -U ibm-watsonx-orchestrate
orchestrate --version
```

## Environment activation

```bash
orchestrate env add -n my_env -u "$WXO_INSTANCE_URL"   # once
orchestrate env activate my_env --api-key "$WXO_API_KEY"
orchestrate env list    # shows the active env
```

The instance URL and API key come from the wxo instance settings page
(API details). Credentials are the user's — never invent or hardcode them.

Tokens expire after a while and every `orchestrate` call then fails with
"The token found for environment '...' is missing or expired". Before asking
the user for the key, **look in the project's `.env`** — `WXO_API_KEY` and
`WXO_URL` are usually already there (source it, don't print it):

```bash
set -a && source .env && set +a
orchestrate env activate <env_name> --api-key "$WXO_API_KEY"
```

## Local smoke test before deploying

The tool module imports `ibm_watsonx_orchestrate.agent_builder.tools`, which is
importable anywhere the ADK is installed. Test the query path locally:

```bash
python -c "
import sys; sys.path.insert(0, 'tool_pkg')
from query_mydata import sql_query_execute
print(sql_query_execute('SELECT COUNT(*) AS n FROM my_table'))
"
```

If the ADK import fails locally, temporarily stub it — the decorator is a no-op
wrapper for local testing purposes:

```bash
python -c "
import sys, types
m = types.ModuleType('ibm_watsonx_orchestrate.agent_builder.tools')
m.tool = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
sys.modules['ibm_watsonx_orchestrate'] = types.ModuleType('ibm_watsonx_orchestrate')
sys.modules['ibm_watsonx_orchestrate.agent_builder'] = types.ModuleType('x')
sys.modules['ibm_watsonx_orchestrate.agent_builder.tools'] = m
sys.path.insert(0, 'tool_pkg')
from query_mydata import sql_query_execute
print(sql_query_execute('SELECT 1 AS ok'))
"
```

## Non-ASCII data (Hebrew/Cyrillic/…): keeping UTF-8 intact

The main corruption source is the ADK itself, and it strikes on ANY OS, UTF-8
macOS included: `orchestrate agents import` reads the YAML through `safe_open`,
which **auto-detects the file encoding with charset_normalizer**. A UTF-8 file
dense with Hebrew or Cyrillic is statistically misdetected (typically as cp855,
DOS Cyrillic), read wrong, and imported mangled — deterministically, every
time, regardless of locale or `PYTHONUTF8`. The fix is the ADK's own override,
set once per machine (stored in `~/.config/orchestrate/config.yaml`):

```bash
orchestrate settings set-encoding utf-8
```

Secondary sources — shell pipelines that assemble files (`echo`, `type`,
clipboard) on non-UTF-8 Windows consoles: write files only with explicit
`encoding="utf-8"`, and export `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` before
`orchestrate` commands. `deploy.sh` applies both the override and the env vars.

Diagnosing mojibake by its signature (what UTF-8 looks like when mis-decoded):

| You see | File was decoded as | Typical source |
|---|---|---|
| `Рђћ` for `—`, `О`-prefixed pairs for Hebrew (`ОћОЋОдОљОЋОф`) | cp855 | Windows console (OEM) |
| `╫`-prefixed pairs (`╫Ф╫Х╫ж`) | cp866 | Russian Windows console |
| `Ч`-prefixed pairs (`Ч”Ч•Ч¦`), `вЂ”` for `—` | cp1251 | Windows ANSI |
| `×`-prefixed pairs (`×”×•×¦`), `â€”` for `—` | latin1/cp1252 | Western locale |

Recovery for an already-deployed mangled agent: the damage is baked into the
imported instructions, not the DB. If the local `agent.yaml` is lost or also
mangled, the corruption is exactly reversible — export the deployed agent
(`orchestrate agents export -n <name> -k native -o out.zip`) and undo the
mis-decode on every string field: `text.encode('cp855').decode('utf-8')`
(swap cp855 for whatever the signature table says). Then, with the encoding
override set, re-import — same agent name updates in place:

```bash
orchestrate settings set-encoding utf-8
orchestrate agents import -f agent.yaml
```

Verify server-side (an export read back as UTF-8 must contain your non-ASCII
values) — a green import log alone does not prove the text survived.

## Embedding the web chat in a site

Out of scope here — use the dedicated `wxo-chat-demo-page` skill: it fetches
the official embed snippet (`orchestrate channels webchat embed`), builds a
demo landing or full-page chat from tested templates, and documents every
known embed failure mode (endless skeleton loaders, CRN 403, security modes).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `orchestrate` crashes with pydantic traceback | Shared Python with conflicting deps — use a dedicated venv (above) |
| `Multiple existing tools found with name ...` | Tool name collision in the tenant — pick a more specific tool name |
| Import rejects package | Hyphens or special chars in package file/folder names — underscores only |
| `attempt to write a readonly database` | You opened without `mode=ro&immutable=1`, or the query is not read-only |
| Tool bundle rejected as too large | Compressed bundle > 50 MB — drop unused columns/sheets, pre-aggregate, or `VACUUM` |
| Agent hallucinates columns | Schema block missing/truncated in agent instructions — regenerate with schema.md baked in |
| Token expired ("missing or expired" on every command) | Re-activate with the key from the project `.env` (`WXO_API_KEY`) — check there before asking the user |
| Agent import rejects welcome message | `welcome_content.welcome_message` is limited to ~100 characters — shorten it |
| Agent's instructions keep "reverting" | Another project imports the same agent/tool name — names are tenant-wide and overwrite silently; merge into one canonical yaml shared by both projects, or rename |
| Hebrew/Cyrillic column names fail in SQL | The agent must double-quote identifiers: `SELECT "имя" FROM t` — this rule is in the agent template |
| Agent shows mojibake (`Рђћ`, `ОћОЋ…`, `Ч”Ч•…`, `×”×•…`) in prompt/answers | ADK's encoding auto-detection misread the yaml (happens on any OS) — run `orchestrate settings set-encoding utf-8` and re-import; see "Non-ASCII data" section for exact recovery |

---
name: excel-to-wxo-agent
description: >-
  Build and deploy a minimal text-to-SQL prototype agent on IBM watsonx
  Orchestrate (wxo) from an Excel or CSV file. Converts the spreadsheet into a
  SQLite database bundled INSIDE the wxo Python tool (no external database to
  deploy), generates the agent YAML with the schema baked into its instructions,
  and imports both via the orchestrate ADK CLI. Use whenever the user wants a
  quick data agent, chat-with-my-Excel prototype, or text-to-SQL demo on watsonx
  Orchestrate — including phrasings like "сделай агента по этому экселю",
  "deploy a data agent to wxo", "прототип text2sql", or any mention of watsonx
  Orchestrate together with Excel/CSV/SQLite data.
---

# Excel → SQLite → watsonx Orchestrate text-to-SQL agent

Goal: from a single Excel/CSV file to a working conversational agent on wxo in
minutes, with zero external infrastructure. The whole trick: the SQLite file is
shipped *inside* the tool package (`orchestrate tools import ... -p <pkg>`
uploads every file in the folder), so there is no database to host, no
connection to configure, no credentials to manage.

Work in a dedicated project folder (e.g. `<data-file-dir>/wxo_agent/`). The
final layout you are building:

```
wxo_agent/
├── tool_pkg/                  # the tool package uploaded to wxo as-is
│   ├── query_<name>.py        # entry file: @tool functions (from template)
│   ├── data.db                # the SQLite snapshot of the Excel
│   └── requirements.txt       # empty (sqlite3 is stdlib)
├── agent.yaml                 # native agent definition
├── schema.md                  # generated schema report (also baked into agent.yaml)
└── deploy.sh                  # import commands
```

## Step 1 — Inspect the file and convert to SQLite

Works with `.xlsx`/`.xlsm` and `.csv` (CSV = one table; `--table` names it).

**Profile big files cheaply — never re-read a 100k-row workbook with pandas
just to look around.** The full read happens exactly once, inside the
converter; before that, reconnaissance costs seconds:

```bash
# 1. sheets × dimensions, instant even on huge files (no data loaded):
python -c "
from openpyxl import load_workbook
wb = load_workbook('<file>.xlsx', read_only=True)
for ws in wb.worksheets: print(ws.title, '|', ws.sheet_state, '|', ws.max_row, 'x', ws.max_column)"

# 2. structure of a candidate sheet — first rows only:
python -c "
import pandas as pd
df = pd.read_excel('<file>.xlsx', sheet_name='<Sheet>', nrows=200)
print(df.dtypes); print(df.head(10))"
```

That tells you which sheets are real tables vs covers/notes, where headers
sit, and what the columns are. Then convert:

```bash
python <skill-dir>/scripts/excel_to_sqlite.py "<file>.xlsx" \
    -o wxo_agent/tool_pkg/data.db [--sheet "Sheet name"] [--table sales]
```

The script sanitizes column names (strips RTL marks and whitespace, keeps
unicode letters), converts dates to ISO-8601 text, skips empty sheets, VACUUMs,
and writes `data.db.schema.md` — a per-column report with types, null %, and
value domains: **that report IS the file profile** — read it instead of
re-querying the data. Move/rename it to `wxo_agent/schema.md`.

Multi-sheet workbooks:
- By default every non-empty sheet becomes its own table (sanitized sheet
  name). Pass `--sheet` (repeatable) to load only the sheets that are real
  tables — skip covers, notes, pivot snapshots and chart sheets spotted
  during reconnaissance.
- Sheets that reference each other (orders + customers, facts + dimension
  lookups) stay separate tables — do NOT pre-join them. Instead, name the
  join keys explicitly in the agent instructions next to the schema ("Заказы
  joins Клиенты on Клиент_ID") so the agent writes correct JOINs.
- Same-structure sheets that are really one dataset split by period/region
  (Jan/Feb/Mar…) are better UNIONed into one table with an added source
  column — do that in pandas before converting.

Other judgment calls the script cannot make for you:
- If a sheet has headers not in row 1 or merged-cell headers, clean it with
  pandas first and feed the script a CSV.
- If the printed DB size warning fires (>50 MB), drop unused columns or
  pre-aggregate — the compressed tool bundle must stay under 50 MB.

Sanity-check the result: open the DB, run one aggregate query, compare a number
against the Excel. A conversion that silently mangled dates or dropped rows will
produce a confidently wrong agent.

## Step 2 — Create the tool package

1. Copy `assets/sqlite_tool_template.py` into `tool_pkg/` and name the file
   after the tool, e.g. `query_sales.py`.
2. Replace every `{{TOOL_NAME}}` with a tenant-unique, data-specific name
   (`query_sales`, not `sql_tool` — tool names collide tenant-wide). The
   template defines two tools: the query executor and a `_schema` fallback.
3. Copy `assets/requirements.txt` into `tool_pkg/` unchanged.
4. Package naming rule: file and folder names inside the package must be
   alphanumeric + underscores only (wxo rejects hyphens).

Smoke-test locally before deploying — import the module and run
`sql_query_execute("SELECT COUNT(*) FROM <table>")` (see
`references/wxo-notes.md` for the one-liner, including an ADK stub if the ADK
is not importable locally). This catches a bad DB path or broken placeholder
replacement in seconds instead of after a deploy.

## Step 3 — Generate the agent YAML

Copy `assets/agent_template.yaml` to `wxo_agent/agent.yaml` and fill the
placeholders: `{{AGENT_NAME}}` (lowercase id), `{{DISPLAY_NAME}}`,
`{{DATA_DESCRIPTION}}` (one line about what the data is), `{{TOOL_NAME}}`, and
`{{SCHEMA}}` — the full `schema.md` content. `{{SCHEMA}}` is multi-line inside
a YAML `|-` block: insert it with every line indented to the block's level
(do it in Python, or write the final YAML directly) — a blind `sed` replace
produces invalid YAML.

Encoding matters as much as syntax: write the file with explicit UTF-8
(`open(..., "w", encoding="utf-8")` or an editor Write tool), and never
assemble it through shell `echo`/`type`/clipboard pipelines — on non-UTF-8
console locales (Windows OEM codepages) those re-encode the text and turn
Hebrew/Cyrillic into mojibake like `ОћОЋ…`/`Рђћ` baked into the deployed
agent. Verify both syntax and content before deploying — pick one non-ASCII
value from `schema.md` and assert it survived:

```bash
python -c "import yaml; d = yaml.safe_load(open('wxo_agent/agent.yaml', encoding='utf-8')); assert '<non-ASCII value from schema.md>' in d['instructions'], 'encoding got mangled'; print('agent.yaml OK')"
```

The schema-in-instructions is what makes the prototype answer well on the first
try: the LLM sees exact tables, columns, and value domains (including
non-English category values it must filter by) without discovery round-trips.
If the schema report is huge (many tables × many columns), trim low-value parts
(long value lists first) rather than dropping whole tables. Keep the SQLite
dialect rules from the template — they prevent the most common failure modes
(LIMIT vs TOP, unquoted unicode identifiers, date functions).

Tailor the starter prompts to the actual data — replace the generic ones with
2–3 questions this specific dataset can answer well. Keep
`welcome_content.welcome_message` under **100 characters** — wxo rejects
longer ones (the template's is sized to fit; watch it when substituting
`{{DATA_DESCRIPTION}}`).

### Ask the user: visualization? (a required question, not an afterthought)

The answer changes the agent PROMPT, so ask it during every agent creation,
before finalizing agent.yaml. Don't decide for the user — the options trade
security against convenience:

1. **COS bucket** — chart images uploaded to IBM COS: production-ready, but
   needs bucket credentials;
2. **Free image hosting** — not available in the marketplace edition (removed
   by policy: chart images must not leave IBM-controlled storage);
3. **Mermaid code in answers** — safe and instant, but ONLY together with a
   renderer page (the `wxo-chat-demo-page` analyst canvas): confirm the user
   plans that page before picking this;
4. **None** (default) — and then add NO chart instructions to the prompt at
   all: an agent without a renderer must answer with tables and text only; a
   raw mermaid block in the standard wxo chat is just noise, and models drift
   into ASCII-art "charts" when charting is mentioned without an outlet.

Setup for each, the bundled chart tool, and the mermaid rules block:
[references/visualization.md](references/visualization.md).

## Step 4 — Deploy to watsonx Orchestrate

Requires the ADK in a clean venv (`pip install ibm-watsonx-orchestrate` — a
shared Python often breaks the CLI with pydantic conflicts, see
`references/wxo-notes.md`) and an activated environment. If no env is active
or the token has expired, **check the project `.env` first** — `WXO_API_KEY`
and `WXO_URL` usually live there (look before asking; never print the values).
Ask the user only when the file has no key — and never invent one:

```bash
orchestrate env add -n proto_env -u "<WXO_INSTANCE_URL>"
orchestrate env activate proto_env --api-key "<WXO_API_KEY>"
```

Then (or use `assets/deploy.sh`, which sets this up itself):

```bash
orchestrate settings set-encoding utf-8      # REQUIRED once per machine: ADK auto-detects file encoding and misreads Hebrew/Cyrillic-heavy UTF-8 as cp855
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8   # guards the rest of the toolchain on non-UTF-8 locales
orchestrate tools import -k python \
    -f wxo_agent/tool_pkg/query_<name>.py \
    -p wxo_agent/tool_pkg \
    -r wxo_agent/tool_pkg/requirements.txt
orchestrate agents import -f wxo_agent/agent.yaml
orchestrate agents list   # verify
```

No `connections add`, no `--app-id` — the bundled DB needs neither.

**Names are tenant-wide and imports overwrite silently.** Before importing,
check `orchestrate agents list` / `tools list`: if the agent or tool name
already exists and this is a DIFFERENT project (not an update of the same
prototype), ask the user — update the existing one or pick a new name. Two
projects sharing a name will keep clobbering each other's instructions with
every deploy, losing whatever the other side added.

## Step 5 — Verify and iterate

Point the user to the wxo chat UI (their instance → Chat → the new agent), or
verify from the CLI that both tools and the agent are listed. Suggest 2–3 test
questions derived from the data.

Iterating:
- **Data changed** → re-run Step 1, then re-run the same `tools import` command
  (same tool name = update in place). The agent YAML does not need re-import.
- **Prompt/schema changed** → edit `agent.yaml`, re-run `agents import` (same
  name = update).

For deeper detail on the bundling mechanism, size limits, local testing stubs,
and a troubleshooting table, read `references/wxo-notes.md`.

<!-- IBM Bob copy. Primary copy: ~/.claude/skills/excel-to-wxo-agent — apply edits to both. -->

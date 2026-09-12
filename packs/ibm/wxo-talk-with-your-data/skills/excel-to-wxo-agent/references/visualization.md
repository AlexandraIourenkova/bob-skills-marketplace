# Optional visualization for the agent

Visualization is OFF by default — it is an extra moving part, and the minimal
prototype works without it. During agent creation, ask the user whether to add
it, and if yes, which of the three variants. Never pick silently: the choice
trades security against convenience.

| Variant | Good for | Why | The catch |
|---|---|---|---|
| **1. COS bucket** (chart images uploaded to IBM Cloud Object Storage) | production-ready demos | safe, renders everywhere the wxo chat renders images | needs bucket credentials (a `cos_connection`) |
| **2. Free image hosting** (litterbox/freeimage) | quick throwaway demos | zero setup, renders everywhere | **very unsafe: chart images with the customer's numbers go to public third-party hosting. Never with real data** |
| **3. Mermaid code in answers** | data demos with a custom page | fast, safe — nothing leaves the answer text | needs a mermaid renderer, which the default wxo UI does NOT have — pair with the `wxo-chat-demo-page` skill's analyst-canvas page |

## Variants 1 & 2 — the chart tool

Both use the same bundled tool, `assets/visualization_tool.py`
(`generate_and_upload_chart`: matplotlib with RTL/Hebrew handling, returns a
Markdown image link the agent embeds in its answer). One switch at the top of
the file selects the mode:

```python
UPLOAD_MODE = "cos"           # default; "free" only for throwaway demos with made-up data
```

Deploy alongside the SQL tool (requirements matter — matplotlib et al.):

```bash
orchestrate tools import -k python \
    -f tool_pkg/visualization_tool.py \
    -r <skill>/assets/visualization_requirements.txt \
    [--app-id cos_connection]        # COS mode only
```

**COS mode** additionally needs a key-value connection with the user's
credentials (ask for them; never invent):

```bash
orchestrate connections add --app-id cos_connection
orchestrate connections configure -a cos_connection --environment draft --type team --kind key_value
orchestrate connections set-credentials -a cos_connection --environment draft \
  -e COS_API_KEY=... -e COS_INSTANCE_CRN=... \
  -e COS_ENDPOINT=https://s3.<region>.cloud-object-storage.appdomain.cloud \
  -e COS_BUCKET=... [-e COS_PUBLIC_ENDPOINT=...]
```

The bucket must allow public reads of uploaded objects (the tool uploads with
`x-amz-acl: public-read` under `charts/<uuid>.png`) — or the links won't open
for the audience.

**Free mode** needs nothing — and that is exactly the problem: images with the
data go to litterbox.catbox.moe (72 h) / freeimage.host. State the risk to the
user explicitly before deploying this mode; refuse it for real company data.

Agent wiring for 1 & 2: add the tool to the agent yaml `tools:` list and add
an instruction to call `generate_and_upload_chart` when a chart helps and
embed the returned `![...](url)` link directly in the answer.

## Variant 3 — mermaid code

No tool at all: append `assets/mermaid_chart_rules.md` to the agent's
instructions (chart-type selection by data shape, strict syntax samples,
distributions as SQL-binned histograms, structural diagrams allowed — plus
two presentation guards learned in testing: charts are ONLY mermaid blocks,
never pseudo-graphics drawn from █/ASCII symbols; and the agent must not tell
the user to copy the code into a renderer — the canvas page renders blocks
automatically, so it just says "The chart:" and emits the block). The agent
then ends chart-worthy answers with a ```` ```mermaid ```` block.

Pick this variant ONLY when the demo includes the analyst-canvas page. If the
user picked no visualization, also make sure the prompt contains no chart
talk at all — mentioning charts without an outlet makes models improvise
ASCII bar charts.

Rendering: the standard wxo chat shows the block as code. The
`wxo-chat-demo-page` skill's **analyst canvas** page intercepts those blocks
and renders them as chart blocks (with an LLM-mermaid repair layer that
tolerates the mistakes models still make even with the rules in place) — use
the two skills together for this variant.

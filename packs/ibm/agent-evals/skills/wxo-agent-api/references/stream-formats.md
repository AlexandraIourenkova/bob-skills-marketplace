# Stream formats, events and step shapes

What the client and `scripts/trace.py` expect on the wire, with the evidence for each part. Evidence markers are the same as in `api-routes.md`: **confirmed-in-code**, **spec-only**, **unverified**. Nothing was observed on a live instance; the probe records what a tenant really sends (`wire_format`, event names, which events carry steps).

## Framing: NDJSON or SSE

**unverified** for the Runs streams. IBM's own material disagrees:
- agentops and the ADK's `_post_nd_json` parse `runs?stream=true` as newline-delimited JSON: one JSON object per line. An SSE `data:` line or a blank line would crash them.
- The IBM async-flow tutorial parses `runs/stream` as SSE `data:` lines and skips `[DONE]`.
- The spec declares `application/json` for both.

v2 chat/completions is SSE `data:` frames (**confirmed-in-code**, agentops 1.6.4), with no `[DONE]`: the stream ends when the connection closes.

The client's parser (`wxo_client.StreamParser`) accepts both framings and a mix of them:
- Lines end in LF, CRLF or CR, even when a line end is split across reads. A leading byte-order mark is dropped.
- A line holding JSON is one NDJSON event.
- SSE `data:` lines accumulate until a blank line or the end of the stream. `event:` names the next event; `id:` persists; `retry:` and `:` comments are ignored.
- When the accumulated `data:` lines do not parse as one JSON document, each line is parsed on its own. The IBM tutorial reads every `data: ` line of `runs/stream` as one event, so a server may send them back to back with no blank line. Only a line that still fails counts as malformed.
- `[DONE]`, as a line or as a data payload, marks the end.
- Other lines are counted, never parsed as events. The verdict is `ndjson`, `sse`, `mixed` or `empty`.

## v1 Runs events

Frame: `{id, event, data}`. Events carry `data.thread_id` and `data.run_id`; one run is one user turn.

Event names:
- Enum in the Hub spec 1.0.9 (**spec-only**): `run.started`, `run.completed`, `run.failed`, `run.expired`, `run.cancelled`, `run.step.started`, `run.step.completed`, `run.step.failed`, `run.step.delta`, `run.step.thinking`, `message.created`, `message.started`, `message.delta`, `message.completed`, `message.interrupt`, `planning`, `flow.slot.listen`, `error`, `done`. The server OpenAPI adds `transcription` and `summary`.
- Outside the enum: `run.created` in Hub examples; `run.step.intermediate` and `slot.input` on the ADK websocket. Unknown names are kept and ignored, never errors.

Where things are:
- Tool steps: `run.step.delta` at `data.delta.step_details[]` (the Hub example names the event; agentops reads any event with `data.delta.step_details`, **confirmed-in-code**).
- A Hub example also shows a tool result as `data.delta {role: "tool", tool_call_id, content}` without `step_details` (**unverified**, hand-written). The trace reads it as a result.
- The answer: `message.created` at `data.message.content[]`. Since ADK 2.2.0 some `message.created` events have no role; the trace skips those. The Hub RunEvent schema types `data.message` as `{key, text}` and puts `content[]` directly under `data`; when `data.message` has no role and no content, the trace reads that list (**spec-only**). Text in `message.delta`, or a plain string `delta.content` in `run.step.delta` (a Hub example, **unverified**), is the fallback.
- The end: `run.completed` or `done` (completed), `run.failed` or `error` (failed), `run.cancelled`, `run.expired`; `flow.slot.listen` ends an async flow's stream. The client stops reading at the first of these, so a server that holds the connection open costs no wait; a read error after one of them counts as a normal end. The probe reads on for 3 s after the first one (or to `[DONE]` or the end of the stream) and records what follows it. The tutorial stops at `message.completed`; whether a turn with tools emits more than one is **unverified**.
- agentops stops reading at the first chunk without `data.thread_id`, waits 10 s and rebuilds the turn from the thread. The tutorial says to take `thread_id` from any event that carries it. So the stream gives timing, and the thread stays the source of truth: the client reconciles the two and warns `stream_thread_mismatch` when they differ.

## Step shapes

The same shapes appear in thread `step_history[].step_details[]`, in v1 `run.step.delta` and in v2 frames (**confirmed-in-code** in ADK and agentops readers; `step_history` itself is untyped in every spec).

| `type` | Fields |
|---|---|
| `tool_calls` | `tool_calls: [{id, name, args}]`, optional `agent_display_name`. One entry can hold several calls |
| `tool_call` (singular, legacy) | `name`, `args`, `tool_call_id` (sometimes `id`) |
| `tool_response` | `name`, `content` (a string, often JSON), `tool_call_id` |
| `thinking` | `content` |
| anything else | kept as an unknown step with its key names; a hand-written Hub example shows `collaborator_call` |

Rules the trace follows, because IBM's own readers break them:
- Read every `step_details` entry. The ADK reads only `[0]`; agentops skips index 1.
- Join a call to its result on `id == tool_call_id`, in either order. For the singular `tool_call`, use `tool_call_id`: agentops' stream parser reads `id` and loses it.
- Never label `thinking` as a tool response, and never drop tool calls on a message whose content is `conversational_search` (agentops does both).
- `args` can be an object or a JSON string; compare them after parsing.

## Hand-offs to collaborator agents

- A hand-off arrives as `[tool_response, tool_call]` in one delta: the response first, both with one `tool_call_id`, the content `Transferring to - <tool>` (Hub example).
- Names: `chat_with_collaborator_<name>` in the default `react_intrinsic` style, `transfer_to_<name>` in `react_prompt` and `react_tools`. agentops only checks for a name ending in `_agent` and misses both.
- The trace flags all three patterns as `handoff: true` and keeps the record. Detection by name is a heuristic.
- A hand-off goal in a case matches either prefix for the same collaborator: the prefix follows the agent style, and v2 names hand-offs `transfer_to_*`.
- In v2, a collaborator's own tool calls are not streamed (Hub). Multi-agent traces are incomplete there.

## v2 chat/completions frames

SSE `data:` frames, each with an `object` field:

| `object` | Carries |
|---|---|
| `thread.run.step.delta` | One step at `choices[0].delta.step_details`: a tool call or a tool result |
| `thread.message.delta` | A chunk of answer text at `choices[0].delta.content` |
| `thread.message.completed` | The final frame: `data.message.step_details[]` with every tool call and result of the turn (left out when no tool ran), `data.message.content`, `choices[0].message.content`, `reasoning_content`, `run_id`, `trace_id`, `thread_id` |
| `error` | The turn failed after the stream began |

- The completed frame is the source of truth, as in agentops 1.6.4. agentops itself warns when it lists fewer steps than were streamed, and the difference is lost: the trace warns `completed_frame_fewer_steps` and lists the calls seen only in step frames. They do not count for recall or precision, but a forbidden tool among them counts as called.
- A stream that ends without a completed frame is rebuilt from the step frames, with the warning `no_completed_frame`.
- A missing `data.message.step_details` means the tools are unknown: either no tool ran or the steps were not shown.

## Answers, widgets and flows

- `content[]` items carry `response_type`:
  - `text`: the answer.
  - `conversational_search`: a knowledge-base answer with `text`, `citations`, `search_results` and `confidence_scores`. It has no `tool_call_id` of its own; the trace attaches it to the last tool step.
  - `option` (with `options[]` and `_meta["com.ibm.orchestrate/widget"]`), `user_input`, `form`, `forms`, `disconnected_apps`, `file_upload`, `date` (a date picker with no text): the agent waits for the user.
- An async flow emits `flow.slot.listen` and the stream ends. The flow keeps running and adds its messages to the thread later; meanwhile the thread record (`GET threads/{id}`) is `async_wait`, then `async_slot_request`, then `ready`, and the thread takes no new user message (IBM async-flow tutorial).
- On the thread route the run itself completes (the ADK waits for `completed`), and its last assistant message is the flow's holding message, marked `additional_properties.display_properties.is_async: true`. The ADK chat detects the flow by that flag, and so does the trace. A run status `async_wait` counts as a flow too.
- The answer leaves a holding message out when another message gives answer text, as the ADK chat does; the part stays in `answer_parts` with `in_answer: false`. `skip_render` is only flagged: its meaning is not documented.
- Widgets, flows (`flow.slot.listen`, `async_wait`, or a last message marked `is_async`) and `requires_input` give the turn status `needs_input`, and `input_request` says why: `widget`, `requires_input` or `async_flow`. The runner and `ask.py` stop a case before its next turn on `async_flow`. Answering a widget from a script is not built in; a scripted next turn may answer it.

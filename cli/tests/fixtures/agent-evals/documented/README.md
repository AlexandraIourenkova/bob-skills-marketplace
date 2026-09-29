# Documented fixtures (set 1)

These files are built by hand from IBM's documented shapes and IBM client code. They were not captured from a live watsonx Orchestrate instance.

Sources:
- IBM API Hub, Agent Execution and Runtime 1.0.9: the POST /runs response, the run record, the runs/stream example (a hand-off as `[tool_response, tool_call]` with one `tool_call_id`, response first), the v2 chat/completions frames and the non-streaming ChatCompletionResponse.
- The watsonx Orchestrate server OpenAPI: the RunEvent enum, ListAgent (`hide_reasoning`, `tools`, `collaborators`) and ToolOut (`input_schema`).
- IBM client code: ADK 2.17 `chat ask` and ai_builder, agentops 1.5.2 and 1.6.4 `get_messages`, the v1 stream parser and the v2 wire module. They define `step_history[].step_details[]` with `tool_calls`, `tool_call`, `tool_response` and `thinking`, the `{data: [...]}` wrapper, `conversational_search` and `option` content, and the MCSP and IAM token responses.
- The IBM async-flow tutorial: SSE `data:` lines for runs/stream and `flow.slot.listen`.

What each file tests:
- `thread-messages.json`: one user message, then two assistant messages. Their step history holds a two-call `tool_calls` entry, two `tool_response` entries in one `step_details` array, a `thinking` step, and a collaborator hand-off pair with the response first.
- `thread-messages-wrapped.json`: the same messages under `{"data": [...]}`.
- `thread-messages-no-steps.json`: an answer without `step_history`. The tools are unknown, not zero.
- `thread-messages-kb.json`: a knowledge-base answer (`conversational_search` with citations) after a search tool call.
- `thread-messages-widget.json`: an `option` widget that needs the user's answer.
- `thread-messages-date.json`: a `date` picker, the AssistantContentType `date` of the Hub (runtime 1.0.9, message-threads 1.0.3). It carries no text, and the message-threads Message schema has no `_meta`, so the content item is the only sign that the agent waits for the user.
- `stream-runs.ndjson` and `stream-runs.sse`: the same events in both framings. The SSE file has `event:`, `id:` and `data:` fields, blank lines, comments and `[DONE]`. One event has no `thread_id` and an unknown name (`run.step.intermediate`). One `message.created` has no role.
- `stream-runs-data-lines.sse`: the same events as one `data: {json}` line each, with no blank line between them. The IBM async-flow tutorial reads `runs/stream` this way (every `data: ` line is one event); the parser must not join the lines into one payload.
- `stream-runs-hub-shapes.ndjson`: the Hub RunEvent shapes the other files lack. `run.step.delta` carries answer text as a plain string in `delta.content` (the Hub `/runs` example), and `message.created` has `data.message` typed `{key, text}` with the `content[]` list directly under `data` (the Hub RunEvent schema).
- `stream-flow-slot.ndjson`: an async flow that ends the stream with `flow.slot.listen`.
- `stream-v2.sse`: v2 frames. The last frame ends at connection close, with no blank line and no `[DONE]`.
- `stream-v2-completed-fewer.sse`: four step frames, but the completed frame lists two steps.
- `chat-completions-nonstream.json`: the stream:false body, with no `step_details`.
- `chat-completions-503-no-threads.json`: the Hub's v2 503 example body, sent when `X-IBM-THREAD-ID` asks for stateful mode on a deployment that keeps no threads.
- `runs-create.json`, `run-status-*.json`, `agents.json`, `tools.json`, `iam-token.json`, `mcsp-token.json`.
- `cases/`: one valid AgentOps Core test case, plus one each with a bad goals DAG, an unknown tool, bad args and a bad `arg_matching`.

All ids, hosts, tokens and names are fake. When a real probe run exists, its sanitized capture goes under `../captured/<saas-aws|ibm-cloud|local>-<date>/`, and the tests also run on it.

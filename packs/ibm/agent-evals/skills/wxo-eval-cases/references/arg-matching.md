# Argument matching

`args` in a `tool_call` goal holds the expected arguments. `arg_matching` maps an argument path to a strategy. A path without an entry is `strict`.

```json
{"type": "tool_call", "name": "get_timeoff-1", "tool_name": "retrieve_timeoff_schedule",
 "args": {"assignment_id": "15338303", "start_date": "2025-01-01", "end_date": "2025-12-31"},
 "arg_matching": {"start_date": "fuzzy", "end_date": "fuzzy"}}
```

## Strategies

| Strategy | The argument in the observed call |
|---|---|
| `strict` | Must be present and equal. The default. |
| `optional` | May be missing; when present, it must be equal. |
| `ignore` | Not checked at all. |
| `fuzzy` | Must be present; the value is compared by meaning. In this pack's runner it goes to the judge queue with the expected and observed values. |

Arguments in the observed call that the goal does not list are allowed. `args: {}` therefore matches any arguments.

## Equality

- This pack's runner compares `strict` and `optional` values as JSON after parsing string arguments that hold JSON. `"2025"` and `2025` differ; `"NWaters"` and `"nwaters"` differ.
- IBM's framework normalises `strict` values before comparing: strings are lowercased, `"10"`, `10` and `10.0` are equal, and list order is ignored. It compares `optional` values as given. For `fuzzy` it tries a date or number comparison, then an embedding or string similarity.
- So a case can pass in one tool and fail in the other. Write expected values the way the agent sends them, and use `fuzzy` or `ignore` where the form varies.

## Nested arguments

- A dotted path addresses a nested argument: `{"filter": {"after": "2025-01-01"}}` with `{"filter.after": "fuzzy"}`.
- A parent path covers its children: `{"filter": "ignore"}` ignores every key under `filter`. A leaf entry wins over its parent's.
- Lists are leaves. `{"tags": "fuzzy"}` works; `tags.0` is not a path.
- `validate` reports an `arg_matching` path that is neither a key of `args`, a dotted leaf path, nor a parent of one. IBM's framework refuses such a case too.

## What to relax

| Argument | Strategy | Why |
|---|---|---|
| Dates and times the agent computes ("next Monday", "this year") | `fuzzy` | The form varies: `2025-01-01`, `2025-01-01T00:00:00Z`, `01/01/2025`. |
| Ids the agent looked up in an earlier call | `strict` | They come from a tool result; a different id is a real error. |
| Ids generated per run (request ids, idempotency keys, timestamps) | `ignore` | They differ on every run. |
| Free text the agent writes (a search query, a message to a collaborator, an email body) | `fuzzy` | The wording varies; the meaning is what counts. |
| Paging and defaults the agent may or may not send (`limit`, `page`) | `optional` | Check them only when present. |
| Enums, flags, amounts, names the user typed | `strict` | A different value changes what the tool does. |

`from-thread` writes every argument strict. Walk through each argument with the user and relax only what the table says varies.

## agentops forms

IBM's framework also reads two older forms. This pack's scorer does not: it would compare them as values, and the goal would always fail. `validate` reports them as errors, with the replacement:

- a value `"<IGNORE>"` skips that argument in agentops: write `arg_matching` `ignore` instead;
- `"args": {"IGNORE": null}` skips every argument in agentops: write `"args": {}` instead.

## What validate checks

- Each `arg_matching` value is one of `strict`, `optional`, `ignore`, `fuzzy`.
- Each `arg_matching` path exists in `args`.
- With a saved catalog, `args` against the tool's `input_schema`: types, `enum`, nested `properties` and `items`, local `$ref`. An argument the schema does not list is an error, because the agent cannot send it. A required argument missing from `args` is a warning: it is simply not checked. Arguments under `ignore` and `<TODO>` placeholders are not type-checked.
- `anyOf`, `oneOf`, `pattern` and `format` in an `input_schema` are not checked.

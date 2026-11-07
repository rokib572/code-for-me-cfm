# State ledger — `.cfm/state.json`

The state file is the machine-readable workflow ledger: which phase is in
flight, where the per-layer pipeline cursor stands, which review gates have
a verdict, what every subagent dispatch cost, what was carried forward,
which configuration questions are still deferred, and how the tracker last
synced. `/cfm:implement-phase` resumes from it in a fresh session with zero
conversation context, so it is updated at every step boundary and must
always be schema-valid. Every operation below is a procedure you follow by
hand with Read, Edit and Write; the field names are unchanged from earlier
cfm versions, so existing ledgers stay valid.

**Used by:** `cfm:implement-phase`, `cfm:diagnose`, `cfm:status`,
`cfm:plan`, `cfm:init`, `cfm:connect-tracker`, `cfm:create-task`,
`cfm:code-review`, `cfm:doctor` (check 9), `cfm:upgrade`.

## 1. Location and lifecycle

- **Path:** the `state_file` key of `.cfm-workflow.yml`, relative to
  the project root. Default `.cfm/state.json`. A broken workflow file still
  gets a ledger: when it does not load, use the default path.
- **Missing file = empty seed.** Treat a missing file as this document and
  never create it just to read it:

  ```json
  {"version": 1, "phase": {"id": null, "status": null}, "deferred_questions": [], "carried_forward": []}
  ```

- **Created** on the first mutating operation (`init` usually; `carry`,
  `question` and `tracker` also create it, since they need no phase).
  Create the parent directory when missing.
- **Unreadable file = error, never replaced.** Invalid JSON reports
  `invalid JSON at line L column C: <reason>`; a non-object top level reports
  `top level must be a JSON object, got <type>`. Show the error, recommend
  `/cfm:doctor`, and do not overwrite.
- **Unknown fields survive every rewrite** (forward compatibility). Never
  drop a key you do not recognise.
- **Timestamps** are ISO 8601 UTC with second precision and a `Z` suffix:
  `YYYY-MM-DDTHH:MM:SSZ`. Get one with `date -u +%Y-%m-%dT%H:%M:%SZ`.

## 2. Schema (v1)

| Field | Type | Values / notes |
|---|---|---|
| `version` | int | always `1` |
| `phase.id` | string or null | kebab slug; non-empty whenever `status` is set |
| `phase.description` | string | one line |
| `phase.plan` | string or null | plan file path (`docs/plans/<slug>.md`) or null |
| `phase.status` | string or null | `null`, `in-flight`, `complete`, `abandoned` |
| `phase.started` | string | ISO timestamp; required whenever `status` is set |
| `phase.completed` | string or null | ISO timestamp; required when `complete` or `abandoned` |
| `cursor.current_layer` | string | a key of `cursor.layers` |
| `cursor.layers.<layer>.coder` | string | `pending`, `dispatched`, `done` |
| `cursor.layers.<layer>.tests.written` | string[] | test file paths |
| `cursor.layers.<layer>.tests.passed` | string[] | test file paths |
| `cursor.layers.<layer>.gates.<agent>` | string | `pending`, `pass`, `fail` (used under `review.scope: layer`) |
| `cursor.phase_gates.<agent>` | string | `pending`, `pass`, `fail` (used under `review.scope: phase`, the default) |
| `files_touched` | string[] | every path a dispatch touched, deduplicated |
| `open_questions` | string[] | resolved before dispatch; empty in flight |
| `deferred_questions[]` | object | `{question: string, asked_by: string, outcome: null|accepted|declined}` |
| `carried_forward` | string[] | every deferred obligation, verbatim, deduplicated |
| `tokens.phase_total` | int | sum of every non-null `total_tokens` |
| `tokens.dispatches[]` | object | see the dispatch entry below |
| `tracker.provider` | string or null | `jira`, `clickup`, `trello`, custom name, or null |
| `tracker.last_sync` | object or null | `{outcome: "ok" | "failed: <reason>", at: ISO}` |
| `tracker.tasks` | object | `"<plan path>#<phase id>": "<provider>:<key>"` — a cache; the plan's binding lines win |
| `notes` | object | free-form `key: string` the next session needs (diagnose's `red_command`, `hypotheses`, `debug_marker`, `root_cause`, …) |
| `pending_gates` | string[] | human gates recorded by `complete` |

A dispatch entry (`tokens.dispatches[]`):

| Field | Type | Notes |
|---|---|---|
| `agent` | string | roster name: `coder`, `e2e-test`, `code-reviewer`, … |
| `model` | string | the workflow file's model id the agent ran with |
| `layer` | string or null | null for phase-scoped reviews |
| `purpose` | string | one line (`review: <scope>` for reviewers) |
| `input_tokens` | int or null | from the usage block, else null |
| `output_tokens` | int or null | from the usage block, else null |
| `total_tokens` | int or null | from the usage block, else null |
| `duration_ms` | int or null | from the usage block, else null |
| `finished` | string | ISO timestamp the result arrived |
| `agent_id` | string | optional; the Agent tool's task id when known |

Annotated example, one layer done, review in progress:

```json
{
  "version": 1,
  "phase": {
    "id": "orders-export",
    "description": "CSV export of an account's orders",
    "plan": "docs/plans/orders-export.md",
    "status": "in-flight",
    "started": "2026-11-07T09:12:04Z",
    "completed": null
  },
  "cursor": {
    "current_layer": "api",
    "layers": {
      "database": {
        "coder": "done",
        "tests": { "written": ["tests/db/test_export.py"], "passed": ["tests/db/test_export.py"] },
        "gates": {}
      },
      "api": { "coder": "dispatched", "tests": { "written": [], "passed": [] }, "gates": {} }
    },
    "phase_gates": { "security-check": "pending", "code-reviewer": "pending" }
  },
  "files_touched": ["src/db/export.py", "tests/db/test_export.py"],
  "open_questions": [],
  "deferred_questions": [
    { "question": "Mirror plans to a tracker?", "asked_by": "cfm:plan", "outcome": null }
  ],
  "carried_forward": ["Rate-limit the export endpoint before GA"],
  "tokens": {
    "phase_total": 48210,
    "dispatches": [
      { "agent": "coder", "model": "claude-sonnet-4-5", "layer": "database",
        "purpose": "export query and row mapper", "input_tokens": 31400,
        "output_tokens": 4810, "total_tokens": 36210, "duration_ms": 184000,
        "finished": "2026-11-07T09:19:40Z" },
      { "agent": "e2e-test", "model": "claude-sonnet-4-5", "layer": "database",
        "purpose": "scoped tests for the export query", "input_tokens": null,
        "output_tokens": null, "total_tokens": 12000, "duration_ms": 91000,
        "finished": "2026-11-07T09:23:02Z" }
    ]
  },
  "tracker": { "provider": null, "last_sync": null, "tasks": {} },
  "notes": {},
  "pending_gates": []
}
```

Review verdicts live in `cursor.phase_gates` when `review.scope` is
`phase` (the default) and in each layer's `gates` when it is `layer`.
Whichever applies, the other stays empty; resume reads the one the
workflow file names.

## 3. Operations

Common rules for every mutating operation:

- Read the file (or start from the seed), apply ONLY the changes the
  operation names, run the validation rules in section 4 against the
  result, then write. Any validation error means **refuse to write** and
  report `refusing to write <state_file>: <error>`.
- When the operation changes nothing, do not rewrite the file.
- "Phase in flight" means `phase.status == "in-flight"`. Operations marked
  *requires a phase* stop with `error: no phase in flight — run init first`
  when it is not.
- "Ensure a layer" means: create `cursor.layers.<layer>` as
  `{"coder": "pending", "tests": {"written": [], "passed": []}, "gates": {}}`
  when it does not exist.
- "Union" means append each item that is not already present, in order;
  never duplicate, never reorder what is there.

### show — pure read

Read the file and present it. A missing file is the seed (no phase).
Never create or modify anything.

### validate — pure read

Apply section 4. Report every error prefixed `error: <state_file>: ` and
every warning prefixed `warning: <state_file>: `. Errors mean the file is
malformed.

### init — start a phase

Inputs: `id`, `description`, `layers` (in the workflow file's order), optional `plan`.

1. Precondition: no phase in flight. Otherwise stop with
   `error: phase '<id>' is in flight — resume it with /cfm:implement-phase, or abandon it first`.
2. `phase` becomes `{id, description, plan (or null), status: "in-flight",
   started: now, completed: null}`.
3. `cursor` becomes `{current_layer: <first layer>, layers: {}, phase_gates: {}}`,
   then ensure every named layer, in order.
4. Reset `files_touched`, `open_questions`, `pending_gates` to `[]` and
   `tokens` to `{"phase_total": 0, "dispatches": []}`.
5. Keep `carried_forward`, `deferred_questions` and `tracker` as they are;
   add them when absent (`[]`, `[]`, `{"provider": null, "last_sync": null, "tasks": {}}`).
   `notes` is also kept, so clear stale keys yourself before a new
   diagnosis.

### dispatch — a subagent was sent

Inputs: `agent`, optional `layer`. *Requires a phase.*

1. With a layer: `cursor.current_layer` becomes it; when the agent is
   `coder`, ensure the layer and its `coder` becomes `"dispatched"`.
2. Without a layer (a phase-scoped reviewer): nothing changes; skip the write.

### record — a dispatch result arrived

Inputs: `agent`, `purpose`, `model`, optional `layer`, `files`,
`tests_written`, `tests_passed`, and the usage numbers. *Requires a phase.*

1. Parse the Agent tool result's `<usage>` block, verbatim, taking only
   numbers it actually reports: `<subagent_tokens>` or `<total_tokens>` →
   `total_tokens`; `<input_tokens>` → `input_tokens`; `<output_tokens>` →
   `output_tokens`; `<duration_ms>` → `duration_ms`. Anything absent is
   `null`. The `model` field is the workflow file's model id the agent was
   dispatched with (the usage block's model line, when present, must agree).
   A foreground result carries its own numbers; a background agent's result
   is its task-notification. A launch acknowledgement is not a result.
   NEVER estimate or invent a count, and never hold the next dispatch to
   wait for one — record nulls, backfill with `usage` later.
2. With a layer: ensure it, `cursor.current_layer` becomes it, its
   `coder` becomes `"done"` when the agent is `coder`, union `tests_written` into
   `tests.written` and `tests_passed` into `tests.passed`.
3. Union `files` into `files_touched`.
4. Append a dispatch entry (all fields of the table in section 2, `finished`
   = now) to `tokens.dispatches`, creating `tokens` when absent.
5. When `total_tokens` is not null, add it to `tokens.phase_total`.

Reviewer dispatches, re-runs and the mechanical-gate included, are
recorded the same way with `purpose: "review: <scope>"` and a null layer
(a layer under `review.scope: layer`), so the report covers the reviews.

### usage — backfill a late result

Inputs: `agent`, optional `layer`, the usage block or numbers. *Requires a phase.*

1. A total is mandatory; otherwise stop with
   `error: usage needs a total (<subagent_tokens> in the block, or an explicit total)`.
2. Find the OLDEST entry in `tokens.dispatches` with this `agent` (and this
   `layer`, when given) whose `total_tokens` is null. None → stop with
   `error: no recorded <agent>[ · <layer>] dispatch is missing usage`.
3. Fill only its null fields among `total_tokens`, `input_tokens`,
   `output_tokens`, `duration_ms`. A reported number is never overwritten.
4. Add the total to `tokens.phase_total`.

### gate — a review verdict landed

Inputs: `agent`, `verdict` (`pass` or `fail`), optional `layer`. *Requires a phase.*

1. Read `review.scope` from the workflow file (default `phase`).
2. Scope `layer`: a layer is mandatory, otherwise stop with
   `error: review.scope is 'layer' — gate needs a layer`; ensure the layer
   and `cursor.layers.<layer>.gates.<agent>` becomes the verdict.
3. Scope `phase`: `cursor.phase_gates.<agent>` becomes the verdict.

A verdict overwrites the previous one for that agent; a re-run of a failed
gate simply records it again.

### rollback — reconciliation moved the cursor back

Inputs: `layer`, `to` (`coder-pending` or `tests-pending`). *Requires a phase.*

1. Ensure the layer.
2. `coder-pending`: its `coder` becomes `"pending"` and `tests` becomes
   `{"written": [], "passed": []}`. `tests-pending`: `tests.passed` becomes
   `[]`; `written` and `coder` stay as they are.
3. `cursor.current_layer` becomes the layer.
4. Reset EVERY gate to `"pending"`: each key of `cursor.phase_gates` and each
   key of every layer's `gates`. A verdict on a diff that has since changed
   is not a verdict.

Record the rollback and its reason in PROGRESS.md as well.

### carry — a deferred obligation

Inputs: one or more items. No phase required.

Union each item, verbatim, into `carried_forward` (create it when absent).
An item already present is not appended again, so repeating a carry is safe.

### question — defer, then resolve in place

Inputs: either `ask <text>` or `resolve` with `outcome` (`accepted` or
`declined`); always `asked_by` (the command that owns asking it, e.g.
`cfm:plan`). Exactly one of ask/resolve; a resolve without an outcome is an
error. No phase required.

- **Ask:** when `deferred_questions` already holds an entry with this
  `asked_by` and a null `outcome`, change nothing (one entry per question,
  never a duplicate). Otherwise append
  `{"question": <text>, "asked_by": <cmd>, "outcome": null}`.
- **Resolve:** find the first entry with this `asked_by`; its
  `outcome` becomes the given value, in place. None → stop with
  `error: no deferred question asked_by '<cmd>'`. Never append a second entry.

### tracker — sync bookkeeping

Inputs: optional `provider`, `last_sync` outcome text, `bind` pairs. No
phase required. When the `tracker` object is absent, it starts as
`{"provider": null, "last_sync": null, "tasks": {}}`.

1. `provider` given: `tracker.provider` becomes that name (the same slug
   `.cfm-workflow.yml` carries under `tracker.provider`); an empty string
   means null, which records a disconnect.
2. `last_sync` given: `tracker.last_sync` becomes
   `{"outcome": <text>, "at": now}`; the text is `"ok"` or `"failed: <one-line reason>"`.
3. Each bind is a pair: a plan phase (`<plan path>#<phase id>`) or a
   task file (`docs/tasks/<slug>.md`), and that item's tracker task key
   (`<provider>:<key>`). A pair missing either half stops with
   `error: bind needs a plan phase or task file and a tracker key`. The
   plan phase or task file becomes a key of `tracker.tasks` whose value is
   the tracker key, replacing an earlier binding for the same item.

`tracker.tasks` is a cache. The binding lines in the plan and task
markdown files are the authority; on disagreement correct the cache from
the markdown, never the reverse.

### note — a free-form phase note

Inputs: `key`, `value`. *Requires a phase.* `notes.<key>` becomes the value
(the `notes` object starts empty when absent), replacing any earlier value
for the key.

### complete — close the phase at the human gate

Inputs: optional `gates` list. *Requires a phase.*

1. `phase.status` becomes `"complete"` and `phase.completed` becomes now.
2. `pending_gates` becomes the given list, or the implementation default
   `["run-verify_full", "git-per-level", "next-phase-approval"]`.
   `/cfm:diagnose` passes `["plan-fix"]`, since a diagnosis leaves no diff.

### abandon — close the phase without a result

*Requires a phase.* `phase.status` becomes `"abandoned"` and
`phase.completed` becomes now. `pending_gates` and everything else stay as they
are; a later `init` resets them.

## 4. Validation rules

Run these over the whole document after every mutation and in doctor
check 9. Each line is the exact error text. Roster checks (marked *roster*)
apply only when `.cfm-workflow.yml` loads: layer names come from
`layers[].name`, agent names from the keys of `agents`.

| Condition | Error |
|---|---|
| top level is not an object | `top level must be a JSON object, got <type>` |
| `version` absent | `version: missing (expected 1)` |
| `version` present but not 1 | warning: `version <v> != 1 — written by a different cfm?` |
| `phase` is not an object | `phase: must be an object` |
| `phase.status` not null/in-flight/complete/abandoned | `phase.status: <value> is not one of ['in-flight', 'complete', 'abandoned'] or null` |
| status set and `phase.id` not a non-empty string | `phase.id: must be a non-empty string when a phase exists` |
| status set and `phase.started` not a string | `phase.started: must be an ISO timestamp when a phase exists` |
| status complete/abandoned and `phase.completed` not a string | `phase.completed: must be set when status is <status>` |
| `cursor` present but not an object | `cursor: must be an object` |
| `cursor.layers` present but not an object | `cursor.layers: must be an object` |
| layer name not in the workflow file (*roster*) | `cursor.layers.<name>: no layer named '<name>' in config` |
| a layer is not an object | `cursor.layers.<name>: must be an object` |
| `coder` not pending/dispatched/done | `cursor.layers.<name>.coder: <value> is not one of ['pending', 'dispatched', 'done']` |
| `tests` not `{written: string[], passed: string[]}` | `cursor.layers.<name>.tests: must be {written: [..], passed: [..]}` |
| layer `gates` present but not an object | `cursor.layers.<name>.gates: must be an object` |
| gate agent not in the workflow file (*roster*) | `cursor.layers.<name>.gates.<agent>: no agent named '<agent>' in config` |
| gate verdict not pending/pass/fail | `cursor.layers.<name>.gates.<agent>: <value> is not one of ['pending', 'pass', 'fail']` |
| `current_layer` set and not a key of `cursor.layers` | `cursor.current_layer: '<value>' is not in cursor.layers` |
| `phase_gates` present but not an object | `cursor.phase_gates: must be an object` |
| phase-gate agent not in the workflow file (*roster*) | `cursor.phase_gates.<agent>: no agent named '<agent>' in config` |
| phase-gate verdict not pending/pass/fail | `cursor.phase_gates.<agent>: <value> is not one of ['pending', 'pass', 'fail']` |
| `files_touched`, `open_questions`, `carried_forward` or `pending_gates` present and not a list of strings | `<field>: must be a list of strings` |
| `deferred_questions` present but not a list | `deferred_questions: must be a list` |
| an entry lacks string `question` or string `asked_by` | `deferred_questions[<i>]: must be {question, asked_by, outcome}` |
| an entry's `outcome` not null/accepted/declined | `deferred_questions[<i>].outcome: <value> is not accepted/declined/null` |
| `tokens` present but not an object | `tokens: must be an object` |
| `tokens.phase_total` not an integer | `tokens.phase_total: must be an integer` |
| `tokens.dispatches` not a list | `tokens.dispatches: must be a list` |
| a dispatch is not an object or lacks string `agent` | `tokens.dispatches[<i>]: must name an agent` |
| `input_tokens`, `output_tokens`, `total_tokens` or `duration_ms` not integer or null | `tokens.dispatches[<i>].<field>: must be an integer or null` |
| `notes` present and not an object of strings | `notes: must be an object of strings` |
| `tracker` present but not an object | `tracker: must be an object` |
| `tracker.tasks` present but not an object | `tracker.tasks: must be an object` |

Values in messages use their JSON spelling in quotes, e.g. `'draft'` or
`None` for null. Absent optional sections (`cursor`, `tokens`, `notes`,
`tracker`, `deferred_questions`) are valid; the seed passes.

Doctor check 9 additionally fails with
`orphaned in-flight phase references missing plan <path>` when an in-flight
phase names a `plan` file that does not exist, and notes
`<state_file> absent — no phase started yet` when there is no file.

## 5. Report — the phase-gate token table

Render this at the phase gate, after `complete`, so the wall-clock time is
final. It is a pure read of `tokens.dispatches` and `phase`.

Transcript harvesting is dropped: the former script read background
task-notifications back out of `~/.claude` session transcripts to fill
missing usage; now every number comes from `record` and `usage` alone.

1. Format numbers: null → `—`; ≥ 1,000,000 → one decimal plus `M`
   (`1.2M`); ≥ 1,000 → one decimal plus `k` (`36.2k`); otherwise as is.
   Format durations: null → `—`; round to whole seconds; `<m>m <s>s` when
   there are minutes, else `<s>s`.
2. One row per dispatch, in ledger order:

   ```markdown
   | Agent | Layer | Model | Input | Output | Total | Duration |
   |---|---|---|---|---|---|---|
   | coder | database | claude-sonnet-4-5 | 31.4k | 4.8k | 36.2k | 3m 4s |
   | e2e-test | database | claude-sonnet-4-5 | — | — | 12.0k | 1m 31s |
   | code-reviewer | review: phase diff | claude-sonnet-4-5 | — | — | — | — |
   | **Totals** | 3 dispatches · 11m 20s | | 31.4k+ | 4.8k+ | 48.2k+ | |
   ```

   Layer shows `purpose` when `layer` is null. A dispatch with a null
   `total_tokens` shows `—` in Total.
3. Totals row: sum each of input, output and total over non-null values;
   suffix the sum with `+` when any dispatch has a null in that column.
   When every dispatch lacks a total, write `not reported` instead of the
   sums. The second cell carries the dispatch count and the phase
   wall-clock (`completed` minus `started`, formatted as a duration; `—`
   when either is missing).
4. When any dispatch has a null `total_tokens`, add after the table:
   `⚠ <n> of <m> dispatches have no usage — backfill with the usage procedure`.
   A warning that survives the gate means a result carried numbers that
   were never recorded; backfill, then re-render.

## 6. Edit discipline

- Read the whole file immediately before every change; never edit from a
  copy you read earlier in the session.
- Change only the fields the operation names. Keep key order and every
  unknown field.
- Write back as pretty JSON, two-space indent, one trailing newline, UTF-8.
- Validate (section 4) before writing; an invalid result is never written.
- Never edit the ledger while a subagent is running; record when its result
  is in hand, in the orchestrator session only. One writer, every boundary.
- A hand-edit that breaks the schema fails doctor check 9; the fix is to
  restore the field, not to delete the file.

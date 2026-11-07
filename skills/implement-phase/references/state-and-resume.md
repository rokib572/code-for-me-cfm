# State schema and resume-with-reconciliation

Two ledgers, one writer (the orchestrator), updated at every step boundary:
`PROGRESS.md` for humans (newest-first, mandatory Carried-forward section)
and the state file for machines. The state file is written ONLY through
the operations in `${CLAUDE_PLUGIN_ROOT}/references/state.md`: each one
validates the result against the schema below before the save, preserves
fields it does not know, and refuses a write that would leave the file
invalid. Doctor check 9 validates the ledger with the same rules, so a
malformed ledger fails the doctor. Workflow resume is NOT session
resume — everything below must work in a fresh session with zero
conversation context.

## State file schema (v1)

Lives at the config's `state_file` (default `.cfm/state.json`). Never
create, edit, or Write it freehand — every row below is an operation in
`references/state.md`, followed by hand with Read, Edit and Write exactly
as that document specifies, and `show` is the only way to read it
(`validate` explains why a file is malformed).

| Boundary | Operation (state.md) and fields |
|---|---|
| phase starts | `init` — id, description, layers (config order), optional plan |
| dispatch sent | `dispatch` — agent, layer |
| dispatch result | `record` — agent, layer, purpose, model, the usage block or its numbers (total, input, output, duration_ms), files, tests_written, tests_passed |
| late usage (backfill) | `usage` — agent, optional layer, the usage block (or an explicit total and duration) — fills the oldest entry for that agent/layer still missing its total; never overwrites |
| gate verdict | `gate` — agent (the reviewer), verdict pass\|fail, layer under `review.scope: layer` |
| reconciliation rollback | `rollback` — layer, to coder-pending\|tests-pending |
| deferred obligation | `carry` — one or more obligations, verbatim |
| free-form phase note | `note` — key, value |
| deferred question | `question` — ask <text> / resolve with outcome accepted\|declined; always asked_by <command> |
| tracker bookkeeping | `tracker` — optional provider, last_sync "ok\|failed: <why>", bind pairs `<plan>#<phase>` → `<provider>:<key>` |
| phase gate | `complete` (or `abandon`); `complete` with gates `plan-fix` is what `/cfm:diagnose` runs, because a diagnosis leaves no diff for the implementation gates to guard |
| phase-gate token table | `report` — a pure read of `tokens.dispatches` and `phase`, rendered as the Markdown table in state.md section 5 |

```json
{
  "version": 1,
  "phase": {
    "id": "kebab-slug",
    "description": "one line",
    "plan": "docs/plans/<file>.md or null",
    "status": "in-flight | complete | abandoned",
    "started": "YYYY-MM-DDTHH:MM:SSZ",
    "completed": "ISO timestamp or null"
  },
  "cursor": {
    "current_layer": "database",
    "layers": {
      "<layer name>": {
        "coder": "pending | dispatched | done",
        "tests": { "written": ["path", "..."], "passed": ["path", "..."] },
        "gates": { "<agent>": "pending | pass | fail" }
      }
    },
    "phase_gates": { "<agent>": "pending | pass | fail" }
  },
  "files_touched": ["path", "..."],
  "open_questions": ["resolved before dispatch — should be empty in flight"],
  "deferred_questions": [
    { "question": "…", "asked_by": "<command that owns asking it>",
      "outcome": "null (still pending) | accepted | declined" }
  ],
  "carried_forward": ["every deferred obligation, verbatim"],
  "tokens": {
    "phase_total": 0,
    "dispatches": [
      { "agent": "coder", "model": "<model id used>", "layer": "database",
        "purpose": "<one-line task>", "input_tokens": "<n or null>",
        "output_tokens": "<n or null>", "total_tokens": "<n>",
        "duration_ms": "<n or null>", "finished": "ISO" }
    ]
  },
  "tracker": {
    "provider": null,
    "last_sync": { "outcome": "ok | failed: <one-line reason>", "at": "ISO" },
    "tasks": { "<plan path>#<phase id>": "<provider>:<task key>" }
  },
  "notes": { "<key>": "<free-form text a resumed session needs>" },
  "pending_gates": ["run-verify_full", "git-per-level", "next-phase-approval"]
}
```

Unknown extra fields must be preserved on rewrite (forward compatibility).

Review verdicts land in `phase_gates` under config `review.scope: phase`
(the default — one pipeline run over the whole phase diff after the last
layer) and in each layer's `gates` under `review.scope: layer`. Whichever
applies, the other stays empty; resume reads the one the config names.

`tracker.tasks` is a CACHE of the phase↔task bindings, for rendering
without re-reading every plan. The binding lines in the markdown files are
the authority (`CONNECTORS.md` Part 2) — on any disagreement, the markdown
wins and the cache is corrected from it, never the other way around.

`deferred_questions` holds ONE entry per question: `asked_by` is the command
that owns asking it, `outcome` is `null` until that command asks and then
records `"accepted"` or `"declined"` by UPDATING the entry in place — never
by appending a duplicate.

## Update discipline

Apply an operation at EVERY boundary: `init` · `dispatch` · `record` (which
marks the coder done, unions `files_touched`, appends the tests and the
token entry) · `gate` · `complete`. A crash between boundaries loses at
most one step, and reconciliation catches even that. Only the orchestrator
writes the ledger, only through these operations, and never while a
subagent is running — record when its result is in hand.

`record` takes only the token and duration numbers the platform ACTUALLY
returned for that subagent, recorded as soon as its result arrives. A
background agent's result is its task-notification, which carries the
`<usage>` block — take it verbatim; a foreground result carries its own
usage. A background launch acknowledgement is not a result: record when
the notification lands. Missing numbers mean null, never a wait for a later
notification — when the numbers arrive, `usage` fills the entry; nothing
reads them back from disk on its own. Reviewer dispatches are recorded the
same way, so the report covers the reviews. When a field is not reported
(e.g. the input/output split), leave it out — the ledger stores `null` and
`report` marks the affected total with "+". NEVER estimate or invent
counts.

## Resume = verify, don't trust

On `/cfm:implement-phase` with no argument and an in-flight phase, run this
BEFORE continuing — the ledger is a claim, not a fact:

1. **Tree check.** `git status --porcelain` (read-only). Files modified on
   disk but absent from `files_touched` — or listed but unchanged/missing —
   mean the ledger drifted: show the difference and let the user decide
   (adopt the stray changes into the phase, or exclude them) before going on.
2. **Parse check.** For every file in `files_touched` that still exists:
   dispatch the mechanical-gate to run the `typecheck` slot (or `lint` if
   no typecheck). No enabled mechanical-gate → skip this check. FAIL → the claimed-done work isn't done.
3. **Test check.** Re-run the state's `tests.passed` files via
   `commands.test_scoped` (dispatch e2e-test with exactly those paths). No enabled e2e-test →
   skip this check.
   A test the ledger says passed that now fails is a rollback trigger.
4. **Roll back on mismatch.** Move the cursor BACK to the last step all
   three checks verify: a layer with failing tests →
   `rollback` — layer <layer>, to tests-pending; a layer whose files
   don't parse → `rollback` — layer <layer>, to coder-pending, for a
   re-dispatch scoped to the broken files. Either rollback resets every
   gate verdict to pending — a review verdict on a diff that has since
   changed is not a verdict. Never advance past an unverified claim.
   Record the rollback and its reason in PROGRESS.md.
5. Report what was verified, what rolled back, and where execution resumes.
   Then continue the normal pipeline from that cursor.

## PROGRESS.md entry format

Prepend (newest first) at the config's `progress_log`:

```markdown
## <YYYY-MM-DD> — <phase id>: <one-line summary> [<status>]

- Shipped: <per layer, one line each>
- Tests: <files written/passed, scoped command used>
- Gates: <agent: verdict, …>
- Tokens: <phase total> (<n> dispatches)

### Carried forward
- <every deferred obligation — debts, skipped cases, open questions>
- (none)
```

The Carried-forward section is mandatory even when empty. Resume reads the
newest entry's Carried-forward to re-surface debts at the next phase gate.

# State schema and resume-with-reconciliation

Two ledgers, one writer (the orchestrator), updated at every step boundary:
`PROGRESS.md` for humans (newest-first, mandatory Carried-forward section)
and the state file for machines. The state file is written ONLY through
`scripts/state.py`: it validates every change against the schema below,
writes atomically, preserves fields it does not know, and refuses a write
that would leave the file invalid. Doctor check 9 runs the same validator,
so a hand-edited ledger fails the doctor. Workflow resume is NOT session
resume — everything below must work in a fresh session with zero
conversation context.

## State file schema (v1)

Lives at the config's `state_file` (default `.cfm/state.json`). Never
create, edit, or Write it by hand — every command below is a
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state.py" --project-dir "$(pwd)" <command>`
call, and `show` is the only way to read it (`validate` explains why a
file is being rejected).

| Boundary | Command |
|---|---|
| phase starts | `init --id <id> --description "<text>" --layers <a> <b> [--plan <path>]` |
| dispatch sent | `dispatch --agent <name> --layer <layer>` |
| dispatch result | `record --agent <name> --layer <layer> --purpose "<text>" --model <id> [--usage BLOCK] [--total N --input N --output N --duration-ms N] [--files ...] [--tests-written ...] [--tests-passed ...]` |
| gate verdict | `gate --agent <reviewer> --verdict pass\|fail [--layer <layer>]` |
| reconciliation rollback | `rollback --layer <layer> --to coder-pending\|tests-pending` |
| deferred obligation | `carry "<text>" ...` |
| free-form phase note | `note --key <k> --value "<text>"` |
| deferred question | `question --ask "<text>" --asked-by <command>` / `question --resolve --asked-by <command> --outcome accepted\|declined` |
| tracker bookkeeping | `tracker [--provider <p>] [--last-sync "ok\|failed: <why>"] [--bind "<plan>#<phase>=<provider>:<key>" ...]` |
| phase gate | `complete` (or `abandon`); `complete --gates plan-fix` is what `/cfm:diagnose` runs, because a diagnosis leaves no diff for the implementation gates to guard |
| phase-gate token chart (stacked bars) | `report` |

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

Call the script at EVERY boundary: `init` · `dispatch` · `record` (which
marks the coder done, unions `files_touched`, appends the tests and the
token entry) · `gate` · `complete`. A crash between boundaries loses at
most one step, and reconciliation catches even that.

`record` takes only the token and duration numbers the platform ACTUALLY
returned for that subagent. For a background agent those arrive in its
task-notification's `<usage>` block — record after that notification, not
on the handback message, and pass the block as `--usage`. When a field is not reported (e.g. the
input/output split), omit the flag — the ledger stores `null` and
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
   no typecheck). FAIL → the claimed-done work isn't done.
3. **Test check.** Re-run the state's `tests.passed` files via
   `commands.test_scoped` (dispatch e2e-test with exactly those paths).
   A test the ledger says passed that now fails is a rollback trigger.
4. **Roll back on mismatch.** Move the cursor BACK to the last step all
   three checks verify: a layer with failing tests →
   `rollback --layer <layer> --to tests-pending`; a layer whose files
   don't parse → `rollback --layer <layer> --to coder-pending` for a
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

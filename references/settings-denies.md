# Settings denies — reference

cfm's permission-layer enforcement is the `permissions.deny` list of the
project's `.claude/settings.json`, derived from `.cfm-workflow.yml` by
Claude following this document. It mirrors the rules a hook once
enforced (secret files, forbidden git operations, the human's
`verify_full` command, the policy files) so the project keeps a layer
that no missing interpreter or hook failure can switch off. The deny set
is OWNED: every rule cfm writes is recorded in a sidecar, a later run
retracts rules the new config no longer needs, and everything the user
wrote is kept verbatim, in place. Nothing here runs a script; Claude
derives the strings below, shows the diff, and writes only on explicit
approval.

Used by: `/cfm:init` (step 5), `/cfm:configure` (after a git-level,
secrets or command change), `/cfm:code-review` (settings generation),
`/cfm:upgrade` (check, then write), `/cfm:doctor` (check 7: missing and
stale denies, sandbox gaps).

## Files

| File | Role | Shape |
|---|---|---|
| `.claude/settings.json` | the project settings Claude Code reads; cfm edits only `permissions.deny` and (opt-in) `sandbox`; it never adds an allow | JSON object; `permissions` and `sandbox`, when present, must be objects |
| `.claude/cfm-denies.json` | the ownership record: the deny list cfm last wrote | `{"deny": ["<rule>", ...]}` — nothing else |
| `.claude/settings.local.json` | the user's personal file; cfm NEVER writes it, only denies Edit on it | untouched |

Minimal settings file after a first run on an empty project:
`{"permissions": {"deny": ["Bash(cat *.env*)", "...", "Read(**/.env*)"]}}`
— pretty-printed as below.

Formatting: two-space indent, keys in the order they already have (new
keys appended), one trailing newline. Every key cfm did not write is
preserved exactly — `customKey`, `env`, `hooks`, a non-string entry in a
rule list, anything.

## Inputs

Read the merged config (`.cfm-workflow.yml` overlaid by
`.cfm-workflow.local.yml`). A config with schema errors is not an input:
stop and report; never derive rules from a config the doctor's check 1
rejects.

| Key | Used for |
|---|---|
| `secret_globs` | the effective list = the file's entries + every default glob below, de-duplicated, file entries first. The defaults are a hard invariant: a file that omits one gets it back |
| `git.level` (`L0`..`L3`, default `L0`) | which git/gh operations are forbidden |
| `forbidden_ops` (top-level list, optional) | extends the forbidden set; can never shrink it |
| `commands.verify_full` (string or list, optional) | the exact command(s) denied to agents |
| `mode`, `profile`, agents, review config | NOT inputs — the permission layer cannot see who is calling; the orchestrator-only rule has no settings shape |

Default secret globs, in order:
`.env*`, `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`,
`*.keystore`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`,
`.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `.htpasswd`,
`.pgpass`, `**/credentials`, `service-account*.json`, `secrets.json`,
`secrets.yml`, `secrets.yaml`, `secrets.toml`, `kubeconfig*`,
`*.tfstate`, `*.tfvars`.

## Rule derivation

Derive the required set in this order; de-duplicate, keeping first
occurrence. Write every string exactly as shown — the doctor compares
them byte for byte.

### 1. Secret globs — Read and Edit

For each glob `G` in the effective list:

- `G` contains no `/` → four rules: `Read(G)`, `Edit(G)`, `Read(**/G)`,
  `Edit(**/G)`.
- `G` contains a `/` (the default `**/credentials`, a user glob such as
  `config/secrets/*`) → two rules: `Read(G)`, `Edit(G)`.

Never emit `Write(...)`: Claude Code consults only Read and Edit path
rules, an Edit rule already covers Write, NotebookEdit and MultiEdit,
and a Write rule is ignored with a startup warning.

Default globs expand to, for example: `Read(.env*)`, `Edit(.env*)`,
`Read(**/.env*)`, `Edit(**/.env*)`, ..., `Read(**/credentials)`,
`Edit(**/credentials)`, ..., `Read(*.tfvars)`, `Edit(*.tfvars)`,
`Read(**/*.tfvars)`, `Edit(**/*.tfvars)`.

### 2. Secret globs — Bash reader heads

For each head `H` in `cat`, `head`, `tail`, `less`, `more`, `source` and
each glob `G`: `Bash(H W)` where `W` is the Bash wildcard of `G`:

1. strip a leading `**/`;
2. if the result does not start with `*`, prefix one `*`.

| Glob | Bash wildcard `W` |
|---|---|
| `.env*` | `*.env*` |
| `*.env`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `*.tfstate`, `*.tfvars` | unchanged |
| `id_rsa*`, `id_dsa*`, `id_ecdsa*`, `id_ed25519*`, `kubeconfig*` | `*id_rsa*`, `*id_dsa*`, `*id_ecdsa*`, `*id_ed25519*`, `*kubeconfig*` |
| `.npmrc`, `.pypirc`, `.netrc`, `.git-credentials`, `.htpasswd`, `.pgpass` | `*.npmrc`, `*.pypirc`, `*.netrc`, `*.git-credentials`, `*.htpasswd`, `*.pgpass` |
| `**/credentials` | `*credentials` |
| `service-account*.json`, `secrets.json`, `secrets.yml`, `secrets.yaml`, `secrets.toml` | `*service-account*.json`, `*secrets.json`, `*secrets.yml`, `*secrets.yaml`, `*secrets.toml` |

So `Bash(cat *.env*)`, `Bash(head *.pem)`, `Bash(source *.env*)`,
`Bash(tail *credentials)`, and so on — six heads times every glob. The
head list is deliberately short; every extra head is one more rule per
glob. The matcher has no carve-outs: printing `.env.example` is denied here
as the Read rule already denies it; an agent that needs the example's
variable names lists them with a pattern search that prints the names
before `=` and nothing after.

### 3. Forbidden git and gh operations

One rule `Bash(<op>:*)` per effective forbidden op. The effective set =
(all mutating ops minus the level's cumulative grants) + the config's
`forbidden_ops` + the always-forbidden ops.

All mutating ops: `git add`, `git commit`, `git push`, `git reset`,
`git rebase`, `git merge`, `git stash`, `git tag`, `git rm`, `git mv`,
`git pull`, `git checkout`, `git switch`, `git restore`, `git clean`,
`git cherry-pick`, `git revert`, `git am`, `git apply`, `git worktree`,
`git submodule`, `git remote`, `git notes`, `git config`,
`gh pr create`, `gh pr edit`, `gh pr comment`, `gh pr close`,
`gh pr review`, `gh issue create`, `gh issue edit`, `gh issue close`,
`gh issue comment`, `gh release`.

Grants, cumulative (L2 includes L1, L3 includes L2):

| Level | Grants |
|---|---|
| `L0` | nothing — every mutating op is denied |
| `L1` | `git add`, `git commit`, `git stash`, `git rm`, `git mv`, `git restore`, `git cherry-pick`, `git revert`, `git am`, `git apply` |
| `L2` | + `git push`, `git checkout`, `git switch`, `git pull`, `git merge`, `git rebase`, `git tag` |
| `L3` | + `gh pr create`, `gh pr edit`, `gh pr comment`, `gh pr review`, `gh issue create`, `gh issue edit`, `gh issue comment` |

Never granted at any level (always in the `Bash(<op>:*)` set):
`git reset`, `git clean`, `git worktree`, `git submodule`, `git remote`,
`git notes`, `git config`, `gh pr close`, `gh issue close`,
`gh release`.

Always-forbidden ops, appended at every level whatever `forbidden_ops`
says: `gh pr merge`, `gh repo delete`, `gh repo edit`, `gh secret`,
`gh variable`, `gh auth`, `git filter-branch`, `git update-ref`,
`git symbolic-ref`, `git replace`, `git reflog expire`, `git gc`.

Examples: at `L0` the set contains `Bash(git commit:*)`,
`Bash(git push:*)`, `Bash(git pull:*)`, `Bash(git checkout:*)`; at `L2`
none of those four, but still `Bash(git config:*)` and
`Bash(gh pr merge:*)`.

### 4. Default-branch push shapes

Only when `git push` is NOT in the forbidden set (so `L2`, `L3`, or a
level override that leaves it out). For each branch `B` in `main`,
`master` and each target `T` in `B`, `*:B`, `*:refs/heads/B`, two
rules: `Bash(git push * T)` and `Bash(git push * T *)`. Both are needed:
a rule with two wildcards does not match the bare form. The twelve
rules, literally:

```
Bash(git push * main)            Bash(git push * main *)
Bash(git push * *:main)          Bash(git push * *:main *)
Bash(git push * *:refs/heads/main)   Bash(git push * *:refs/heads/main *)
Bash(git push * master)          Bash(git push * master *)
Bash(git push * *:master)        Bash(git push * *:master *)
Bash(git push * *:refs/heads/master) Bash(git push * *:refs/heads/master *)
```

Limit: only literal shapes are expressible. `git push origin main`,
`git push -u origin main` and `HEAD:main` are caught; a bare `git push`
while `main` is checked out, or a ref built at runtime, is not. Say so
when the user asks what the layer covers.

### 5. Hard invariants — at every level

Append these 28 rules unchanged, every level, every config:

```
Bash(git push -f *)                    Bash(git push * -f *)
Bash(git push --force *)               Bash(git push * --force *)
Bash(git push --force-with-lease *)    Bash(git push * --force-with-lease *)
Bash(git push --force-if-includes *)   Bash(git push * --force-if-includes *)
Bash(git push --delete *)              Bash(git push * --delete *)
Bash(git push -d *)                    Bash(git push * -d *)
Bash(git push --mirror *)              Bash(git push * --mirror *)
Bash(git push --prune *)               Bash(git push * --prune *)
Bash(git branch -D *)                  Bash(git branch * -D *)
Bash(git branch -d *)                  Bash(git branch * -d *)
Bash(git branch --delete *)            Bash(git branch * --delete *)
Bash(git branch -m *)                  Bash(git branch * -m *)
Bash(git branch -M *)                  Bash(git branch * -M *)
Bash(git branch --move *)              Bash(git branch * --move *)
```

### 6. The human's verify command

For each entry of `commands.verify_full` (a string counts as a
one-element list), trimmed of surrounding whitespace: `Bash(<command>)`
— the exact text, no `:*` suffix. `verify_full: npm test` →
`Bash(npm test)`. Absent slot → no rule. Limit: aliases pass
(`npm run test`, `npx jest`); the rule matches the configured text only.

### 7. No self-denies in this edition

Earlier cfm versions ended the list with Edit denies on
`.claude/settings.json`, `.claude/settings.local.json` and
`.claude/cfm-denies.json`, written by a script that bypassed them. This
edition writes the files by hand through the procedure below, so those
three rules are not generated; a project that still carries them from an
earlier version keeps them (they are not stale), and the human applies
any later update to the settings pair themselves when the denies refuse
the Edit. What protects the layer now: every deny is written only after
the human approves the diff, the shipped agent files grant reviewers no
Edit tool at all, and Claude Code prompts before an edit to a settings
file in any case.

## Ownership and retraction

The sidecar `.claude/cfm-denies.json` records the complete required set
of the last write — `{"deny": [...]}` in derivation order. It is what
lets a later run tell cfm's rules from the user's.

On every run, compute three lists against the current settings:

- **required**: sections 1–6 for the current config.
- **owned**: the sidecar's `deny` list, unioned with the
  **level-independent universe** — every rule cfm could write without
  knowing the config: the Read/Edit/Bash rules of the DEFAULT globs
  (sections 1–2), `Bash(<op>:*)` for EVERY mutating and always-forbidden
  op, the twelve push shapes, the 28 invariants, and the three Edit
  self-denies earlier versions wrote (owned so they are never counted
  as the user's, never stale).
  This covers a project whose sidecar is absent or unreadable (an
  unreadable sidecar only loses precision; it never blocks the run).
- **stale**: entries of the current deny list that are owned and not
  required, in their current order.

Merge rule for `permissions.deny`: keep every existing entry verbatim
and in place, dropping only the stale ones; then append the missing
required rules, sorted. `permissions.allow` is never touched. A deny the user wrote outside cfm's shapes
(`Bash(rm -rf /)`, `Read(./secrets/**)`) is never touched, never
reordered. A user deny that coincides with a cfm shape is kept while
required and retracted once not required — the layer cannot tell the two
apart, so say this when retracting a rule the user may have wanted.

Why retraction is mandatory: raising the level from `L0` to `L2` must
remove `Bash(git push:*)`, `Bash(git checkout:*)` and the rest of the
newly granted ops and ADD the twelve push shapes. Append-only would
leave the level change silently ineffective at this layer.

After a write, the sidecar is rewritten to exactly the new required
list. Rules a user glob, a config `forbidden_ops` entry or `verify_full`
produced are owned only through the sidecar — if it is lost, a later
config change cannot retract them; the user removes them by hand.

## Check (what the doctor and `/cfm:upgrade` do)

A check never writes. Report, then exit red or green:

- **missing**: each required rule absent from `permissions.deny` — red.
  When the config itself has schema errors, report as a warning and let
  the schema check own the failure.
- **stale**: each owned, no-longer-required rule still present — red
  ("the permission layer contradicts the config").
- **sandbox** (only when the sandbox is on, or the check was asked with
  it): `enabled` not `true`, or any cfm `denyRead`/`denyWrite` path
  missing — the doctor warns; `/cfm:upgrade` treats it as a finding.

Green means: every required deny present, no stale cfm deny, and (when
on) the sandbox block complete.

## Sandbox — the OS-level layer (opt-in)

Offer once, in `/cfm:init`, `/cfm:configure` and `/cfm:code-review`;
include it in every later run while it is on, so its entries follow the
config. It enables Claude Code's Bash sandbox in the PROJECT settings:
the operating system then enforces the paths on the running process and
its children, which closes the interpreter (`python3 -c "open('.env')"`),
variable (`f=.env; cat $f`) and script-file evasions the text rules
concede.

Block to merge into `.claude/settings.json`:

```json
{
  "sandbox": {
    "enabled": true,
    "filesystem": {
      "denyRead": ["./.env*", "./**/.env*", "./*.env", "./**/*.env", "..."],
      "denyWrite": [
        "./.cfm-workflow.yml",
        "./.cfm-workflow.local.yml",
        "./.claude/cfm-denies.json"
      ]
    }
  }
}
```

Derivation:

- `enabled`: always set to `true` (an existing `false` is flipped — that
  is the opt-in).
- `denyRead`: for each effective secret glob, strip a leading `**/` to
  get `bare`, then `./bare` and `./**/bare`, in glob order, no
  duplicates. `**/credentials` → `./credentials`, `./**/credentials`.
  `./` resolves to the project root in project settings.
- `denyWrite`: exactly the three paths above — the config pair and the
  sidecar. The settings files and `.claude/agents` are on the sandbox's
  own built-in protected list; do not repeat them.
- Merge: existing `filesystem` entries (`allowWrite`, a user's
  `~/.ssh` in `denyRead`) stay first and in place; cfm's paths are
  appended when missing. Other `sandbox` keys are untouched.
- The sidecar does not record sandbox entries; the check derives them
  from the config each time.

Platform notes: macOS, Linux and WSL2. Linux needs `bubblewrap`; `/sandbox`
shows what is missing. The sandbox adds network prompts of its own.
After writing, tell the user to verify the resolved paths in `/sandbox`
→ Config. With the sandbox on, Bash writes to `.claude/settings.json`
are blocked by the built-in list as well — then hand the human the
exact JSON to paste rather than fighting the layer.

## Procedure — propose, diff, approve, write

1. Load the merged config; stop on schema errors.
2. Read the current `.claude/settings.json` (absent → `{}`). Unparseable
   JSON, a non-object top level, or a non-object `permissions`/`sandbox`
   → stop: "cannot parse existing settings — refusing to touch it".
   Never clobber a file you cannot parse.
3. Read the sidecar; absent or unreadable → `[]`.
4. Derive required, owned, stale; build the proposed document (merge
   rules above; sandbox block when on or requested).
5. Show a unified diff of the current file against the proposed one and
   list the retractions by name ("retracted 4 stale denies: ..."). Say
   in one line that cfm's recorded rules are retracted and everything
   the user wrote is kept in place.
6. Write ONLY on explicit approval, atomically: the full document to a
   temp file inside `.claude/`, rename over `settings.json`; then the
   sidecar the same way. Two-space indent, trailing newline. Write the
   pair together — a settings file without its sidecar has lost
   ownership of every non-default rule.
7. Re-run the check (the doctor's check 7) and show it. If the user
   declines, say in one line that check 7 stays red until the denies
   exist.

This edits a repo file: the team sees it in `git diff`. Show the added
rules the way any config diff is shown — never write first.

## Retired — status line

`--statusline` is dropped: it wrote a `statusLine` entry pointing at a
shipped shell script, and the plugin ships none; leave any existing
`statusLine` key untouched and ignore a `statusline` key in an old
sidecar.

## Limits to state when asked

- Text rules only: recursive readers that never name the file
  (`grep -r SECRET .`, `find . -exec cat {} +`, `xargs cat`, `tar`) pass;
  symlinks are not resolved. The sandbox is the answer, not more rules.
- The orchestrator-only rule has no settings shape: the permission
  layer cannot see which agent is calling.
- `.cfm-workflow.yml` itself has no deny: the main session writes it
  with the same tools. The sandbox's `denyWrite` is the only layer on
  it, and it covers Bash alone.
- Content arriving from git history (`git checkout`, `git merge`,
  `git pull` at a level that grants them) can change a policy file
  without naming it. The real rule: never put real secrets where an
  agent works.

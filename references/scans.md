# cfm scans — init classification, debt ledger, disabled-agent references

Three pure reads, done by hand with Glob, Grep and Read. The init scan
classifies a repo and collects the evidence that beats guesses during
config genesis. The debt scan harvests `cfm-debt:` markers so a deferral
cannot quietly become permanent. The reference sweep finds where project
prose still names an agent the config has disabled. None of them writes.

**Used by:** `cfm:init` step 1 (init scan); `cfm:status` Carried-forward
and `cfm:implement-phase` phase gate (debt scan); `cfm:configure` step 5
and `cfm:upgrade` (reference sweep).

Throughout, "ignored dirs" means: `.git node_modules vendor dist build out
target .venv venv __pycache__ .next .nuxt .turbo coverage .idea .vscode bin
obj` (the debt scan adds `.mypy_cache .pytest_cache`). Paths are
repo-relative with `/` separators.

## Init scan

### Signals — collect every one, in this order

1. `has_cfm_config` — `.cfm-workflow.yml` exists at the root.
2. `git_repo` — `.git/` is a directory at the root.
3. `manifests` — each of these present at the root, in this order:
   `package.json pyproject.toml setup.py requirements.txt go.mod Cargo.toml
   composer.json Gemfile pom.xml build.gradle build.gradle.kts mix.exs
   pubspec.yaml Makefile justfile Taskfile.yml`; then every `*.csproj`,
   `*.sln`, `*.fsproj` anywhere in the tree (Glob `**/`), sorted, skipping
   any path with an ignored dir in it.
4. `lockfiles` — each present at the root: `package-lock.json pnpm-lock.yaml
   yarn.lock bun.lockb poetry.lock uv.lock Pipfile.lock go.sum Cargo.lock
   composer.lock Gemfile.lock`.
5. `ci_files` — for `.github/workflows` list its `*.yml` and `*.yaml`
   (sorted); for `.gitlab-ci.yml .circleci/config.yml azure-pipelines.yml
   Jenkinsfile bitbucket-pipelines.yml .travis.yml` list the path if it
   exists.
6. `package_json_scripts` — the `scripts` object of root `package.json`,
   `{}` if absent or unparseable.
7. `source_files`, `test_files`, `top_dirs` — walk the tree, pruning
   ignored dirs and every dir whose name starts with `.`. `top_dirs` is the
   sorted list of surviving root-level dirs. A source file has one of these
   extensions (case-insensitive): `.ts .tsx .js .jsx .mjs .py .go .rs .cs
   .php .rb .java .kt .ex .exs .dart .vue .svelte .c .cc .cpp .h .swift
   .scala .sql`. Count it as a test when its lowercased name contains
   `.test.`, `.spec.` or `_test`, starts with `test_`, or any dir on its
   path is one of `tests test __tests__ e2e spec`.
8. `claude_setup` — six sorted lists: `claude_md` (every `CLAUDE.md` at
   the root or below, skipping ignored dirs), `agents`
   (`.claude/agents/*.md`), `commands` (`.claude/commands/*.md`), `skills`
   (`.claude/skills/*/SKILL.md`), `rules` (`.claude/rules/*.md`),
   `settings` (`.claude/settings*.json`).
9. `doc_candidates` — shallow listing of `.md` files in, in order, the
   root, `docs/`, `doc/`, `.github/` (root first; an earlier dir wins
   ties). Compare lowercased names:
   - progress, strong: exactly `progress.md status.md journal.md devlog.md
     history.md worklog.md`; weak: `changelog.md` (releases, not a work
     ledger). Output `progress` = strong then weak.
   - rules, weak: `contributing.md` (process, not rules); strong: the stem
     contains `rule`, `convention`, `guideline`, `styleguide` or
     `style-guide`. Output `rules` = strong then weak.
   `.claude/rules/*.md` is deliberately excluded here; `claude_setup`
   already lists it.

### Decision rules — first match wins

| order | rule | `scenario` |
|---|---|---|
| 1 | `has_cfm_config` | `already-initialized` |
| 2 | any `claude_setup` list is non-empty | `adoption` |
| 3 | no manifests AND `source_files` is 0 | `greenfield` |
| 4 | `source_files` < 15 | `scaffolded` |
| 5 | otherwise | `existing` |

`scenario_note` is non-empty only for `scaffolded` and `existing`:
"scaffolded-vs-existing is a heuristic (threshold: 15 source files) —
confirm with the user". Fewer than 15 source files reads as boilerplate,
not features; the init skill always asks which it is.

### Output

Report `scenario`, `scenario_note`, and `signals` with exactly the keys
above: `has_cfm_config git_repo manifests lockfiles ci_files
package_json_scripts source_files test_files top_dirs claude_setup
doc_candidates`. The init skill routes on `scenario`, pre-fills layers
from `top_dirs`, derives commands from `manifests` and
`package_json_scripts`, and asks about ledgers only when `doc_candidates`
has entries.

## Debt scan

### What a marker is

A line whose comment prefix is followed by `cfm-debt:`. Accepted
prefixes: `#`, `//`, `--`, `/*`, `*`, `<!--`, `;`, `%`, each followed by
optional whitespace. Grep pattern:
`(#|//|--|/\*|\*|<!--|;|%)\s*cfm-debt:`. The prefix is required so prose
that merely names the convention stays out of the ledger. A trailing `*/`
or `-->` is not part of the body.

The body is `<ceiling>, <upgrade trigger>`: strip whitespace and a
trailing `.`, split on the FIRST comma. `ceiling` is the left half,
`upgrade` the right. `no_trigger` is true when there is no comma or the
right half is empty, and when the body is blank.

### What to scan

- Whole repo (`scanned: "repo"`): walk from the root pruning ignored
  dirs. Skip a file when its extension is one of `.png .jpg .jpeg .gif
  .svg .ico .pdf .zip .gz .tar .woff .woff2 .ttf .eot .mp4 .mp3 .wasm .pyc
  .so .dylib .dll .exe .lock`, when it is a symlink, or when it is larger
  than 2,000,000 bytes (generated, not authored).
- Scoped (`scanned: "paths"`, the phase gate): only the listed
  repo-relative paths; skip any that is not a regular file.
- **Secret-glob exclusion, both modes:** never open a file whose path or
  basename matches a glob in config `secret_globs`. That list is the
  config's `secret_globs` unioned with the defaults: `.env* *.env *.pem
  *.key *.p12 *.pfx *.jks *.keystore id_rsa* id_dsa* id_ecdsa*
  id_ed25519* .npmrc .pypirc .netrc .git-credentials .htpasswd .pgpass
  **/credentials service-account*.json secrets.json secrets.yml
  secrets.yaml secrets.toml kubeconfig* *.tfstate *.tfvars`. A missing or
  broken config does not disable the skip: fall back to the defaults.
- Known limit: a comment-prefixed example in documentation is
  indistinguishable from a real marker. A whole-repo scan of a repo that
  documents the convention sees its own examples; the phase gate is
  unaffected because it is scoped to touched files.

### Output

Sort hits by `(file, line)`. Report `marker` (`cfm-debt:`), `scanned`
(`repo` or `paths`), `markers` as a list of `{file, line, ceiling,
upgrade, no_trigger}`, `total` (count), `no_trigger` (count with
`no_trigger` true).

### Carried-debt items it produces

- `cfm:status`: one line `<total> cfm-debt markers, <no_trigger> with no
  upgrade trigger`, then each `no_trigger` marker as `file:line —
  <ceiling>`. Zero markers renders nothing.
- `cfm:implement-phase` phase gate (scoped to touched files): each marker
  as `file:line — <ceiling>; revisit when <upgrade>`, tagged **no
  trigger** when `no_trigger` is true. Each becomes a carried obligation in
  the progress log entry and the state ledger.

## Reference sweep (disabled agents)

### Preconditions

Read `.cfm-workflow.yml` RAW. Do not use the merged config: the loader
drops disabled agents, and this sweep needs their names. Missing,
unparseable, empty, or non-mapping file: report the error and stop.

### Which agents

Every key under `agents` whose entry is a mapping with `enabled: false`,
sorted. No such agent: report `no references to disabled agents`.

### Which files, in this order, deduplicated

1. `CLAUDE.md`
2. `.cfm-workflow.local.yml`
3. every string in config `claude_md.files`
4. config `rules_file` (default `.claude/rules/rules.md`) and
   `context_file` (default `CONTEXT.md`)
5. every file under `.claude/` recursively (dirs and names sorted) except
   `settings.json` and `settings.local.json` (those belong to the
   settings-denies procedure)

Skip a path that is a symlink or not a regular file, and a file that is
not valid UTF-8. Never scan the progress log, plans, or the state file:
they record what happened, not what runs.

### What counts as a reference

- For `.claude/agents/<name>.md` where `<name>` is a disabled CUSTOM agent
  (not a shipped plugin agent, i.e. no `agents/<name>.md` in the plugin):
  the whole file is one hit, `line` null, text "the disabled custom
  agent's own file". Do not scan its lines.
- Otherwise, each line containing the agent name as a whole token: not
  preceded or followed by a word character or `-`. Grep pattern per name:
  `(?<![\w-])<name>(?![\w-])`. One hit per (line, agent); a line naming
  two disabled agents yields two hits.

### Output

`disabled` (the sorted names) and `references` as a list of `{agent,
path, line, text}` with `text` the stripped line. Human form:
`<path>[:<line>]: <agent> — <text>`. The consuming skill proposes one diff
per file, applied only on approval, following `/cfm:configure` step 5
(prose deleted, rule enforcement reassigned never deleted, local override
blocks dropped, a disabled custom agent's file deleted).

# Redaction reference

Everything that leaves the repo — a tracker title, body, comment, label,
a phase-gate note, a diagnose loop's output shown in the transcript —
passes through this pass first. It is the single source of the redaction
patterns: apply it by hand, exactly as written, and send only the result.
Nothing else may carry a pattern list of its own. The policy is DROP, not
truncate: a match becomes the literal text `[redacted]`, and no step of
the pass ever quotes the matched content back — not in a warning, not in
a count, not in a question to the user.

**Used by:** `/cfm:plan`, `/cfm:create-task`, `/cfm:implement-phase`,
`/cfm:connect-tracker`, `/cfm:diagnose`, and the adapter contract in
`CONNECTORS.md` Part 2.

## Fail closed

If the pass cannot be completed — the payload is too long to read in
full, a family cannot be applied with confidence, the result cannot be
shown — post NOTHING for that payload. Emit a one-line local warning and
continue the workflow; the markdown files are canonical and a missed sync
is never a blocker. When unsure whether a string is a credential, drop
the whole paragraph and note `[redacted]`. Never post the unredacted
draft "just this once".

## The pass, step by step

1. Draft the payload in full before redacting anything.
2. Apply the families below **in the order listed** — whole blocks first,
   provider token shapes, then headers and URLs, then the keyed-value
   forms last (quoted-JSON before colon forms). Later families see the
   earlier families' output, so `"password": "[redacted]"` is not
   re-matched by the colon form.
3. For every keyed-value match, run the exemption check before replacing.
   An exempt value stays byte-identical and is not counted.
4. Count each real replacement by family name.
5. If any count is non-zero, show the user the redacted result (never
   the draft) before the tracker call, in the form
   `redacted N match(es): <family> (n), <family> (n)`.
6. Send only the redacted text. In the tracker bookkeeping line
   (the `tracker` operation's `last_sync` value in `references/state.md`)
   append the total, e.g. `last_sync: "ok (2 redacted)"`; `"ok"` alone
   means zero.
7. The pass is idempotent: running it again on its output changes
   nothing. If a second pass would change something, the first was wrong
   — redo it.

## Credential key words

The keyed-value families match a key that **contains** one of:

```
secret | token(?![a-z]) | password | passwd | api_?key | private_?key
| credential | authorization | auth(?![a-z])
```

- Matching is case-insensitive in the env and JSON forms.
- `token` and `auth` end at a letter boundary: the next character must
  not be a letter (any case). So `TOKENIZER`, `author`, `AUTHOR`,
  `git_author`, `MAX_TOKENS` are not keys; `authtoken`, `oauth_token`,
  `AUTHORIZATION`, `token_secret`, `AUTH_HEADER` still are.
- `secret` is open-ended: `secrets`, `client_secrets`, `db_secret_v2`
  all match.
- Colon forms additionally accept a hyphen in `api-key` / `private-key`.

## Exemptions — apply to the keyed-value families only

A keyed match is left untouched when the **whole value** (trailing
whitespace ignored) is one of:

1. `[redacted]` already.
2. `true`, `false`, `null` (any case).
3. A setting literal (any case):
   `required optional none null enabled disabled yes no on off basic
   bearer digest oauth oauth2 jwt hmac hs256 hs384 hs512 rs256 rs384
   rs512`.
4. A bare variable reference `${NAME}` and nothing else. A default
   (`${pw:-hunter2default}`) is a value and IS redacted.
5. A plain number (`30`, `3600`, `1.5`) — UNLESS the key contains
   `password`, `passwd` or `pin` (any case): `password: 123456` and
   `API_PIN_PASSWORD=8675309` are redacted.
6. **Env and colon forms only:** the key's last word (the part after the
   final `_`, `.` or `-`, or the whole key) says the value is a location,
   a name, a policy or a setting:

   ```
   glob globs file files path dir url uri provider type name rotation
   ttl expir* length prefix scheme issuer audience alg algorithm
   reporting enabled required timeout count limit method mode source
   version
   ```

   So `secret_globs: [.env*]`, `credentials_file: config/app.ini`,
   `api_key_rotation: monthly`, `TOKEN_URL=https://...`,
   `oauth_provider=google`, `token_reporting=false`, `auth_timeout: 30`
   are untouched. `header` is deliberately NOT in the list:
   `AUTH_HEADER=Basic abcdef` → `AUTH_HEADER=[redacted]`.
   This suffix rule does not apply to the quoted-JSON form:
   `"credentials_file": "config/app.ini"` → `"credentials_file": "[redacted]"`.
   Only exemptions 1–5 apply there (`"token_type": "Bearer"` stays).

Exemptions are anchored to the whole value, never the line:
`password: hunter2 [redacted]` → `password: [redacted]`, and
`PASSWORD=realLeak42  # will be [redacted] in the ticket` → `PASSWORD=[redacted]`.

## Pattern families, in application order

Replacement is `[redacted]` for the entire match unless a family says
what it keeps.

1. **pem-block** — `-----BEGIN [A-Z0-9 ]*-----` through the first
   `-----END [A-Z0-9 ]*-----`, across lines, inclusive. Drop whole block.
2. **pem-block-truncated** — a `-----BEGIN ...-----` marker with no END,
   when EITHER the label contains `PRIVATE KEY`, OR one of the next two
   lines starts (after optional whitespace) with 40+ chars of
   `[A-Za-z0-9+/=]`. Drop from the marker to the END OF THE PAYLOAD.
   Prose such as `Do not paste -----BEGIN CERTIFICATE----- blocks into
   tickets.` followed by ordinary text survives.
3. **jwt** — `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}`
4. **jwt-partial** — `eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{7,}`
5. **aws-access-key-id** —
   `(?:A3T[A-Z0-9]|AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}`
   (no word boundary: the first 20 chars of a longer run are dropped).
6. **gitlab-token** — `glpat-[A-Za-z0-9_-]{20,}`
7. **npm-token** — `npm_[A-Za-z0-9]{36}`
8. **slack-webhook** —
   `https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9_]+`
   (whole URL dropped).
9. **slack-app-token** — `xapp-[0-9]-[A-Za-z0-9-]{10,}`
10. **azure-connection-key** — case-insensitive, at a word boundary:
    `(AccountKey|SharedAccessKey|SharedAccessSignature|sig)=` followed by
    a value up to the next `;` or whitespace. Keep `Name=`, drop the
    value: `AccountKey=[redacted]`. `AccountName=x` and the endpoint
    suffix survive.
11. **secret-key-token** — `sk[-_][A-Za-z0-9_-]{20,}` not preceded by a
    letter or digit (`sk-proj-…`, `sk_live_…`; `desk_…` is not one).
12. **slack-token** — `xox[a-z]-[A-Za-z0-9-]{10,}`
13. **github-token** — `gh[pousr]_[A-Za-z0-9]{36}`
14. **github-fine-grained-pat** — `github_pat_[A-Za-z0-9_]{22,}`
15. **google-api-key** — `AIza[0-9A-Za-z_-]{35}`
16. **authorization-header** — case-insensitive
    `Authorization\s*:\s*(Bearer|Basic|token)\s+<non-space run>`. Keep
    the header name and scheme, drop the credential:
    `Authorization: Bearer [redacted]`, `Authorization: Basic [redacted]`.
    An already-redacted header is left alone.
17. **url-credentials** —
    `(?P<scheme>[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^@\s]+@`. Keep the
    scheme and everything after `@`, drop `user:pass@` as a unit:
    `postgres://user:hunter2pass@db.example.com/app` →
    `postgres://[redacted]@db.example.com/app`. The user name goes too.
18. **keyed-json-value** — anywhere on a line, case-insensitive:
    a quoted key (`"` or `'`) that contains a key word, optional spaces,
    `:`, optional spaces, a quoted value (same or other quote, escapes
    allowed, no newline). Keep key and quotes, replace the value:
    `"password": "it'sSecret77"` → `"password": "[redacted]"`,
    `'password': 'fakepw99'` → `'password': '[redacted]'`. Works inside a
    one-line object: `{"a": 1, "api_key": "x", "b": 2}`. Unquoted JSON
    values (`"retries": 30`, `"token": null`) are not matched.
19. **keyed-env-value** — a whole line, case-insensitive:
    optional indent, optional `export `, key `[A-Za-z0-9_]*<key word>[A-Za-z0-9_]*`
    (no hyphens), optional spaces, `=`, optional spaces, then the rest of
    the line (first char non-space). The whole remainder is the value,
    trailing comment included. Keep up to and including `=`:
    `API_KEY=abc123def456` → `API_KEY=[redacted]`,
    `AUTHORIZATION=Bearer abcdef` → `AUTHORIZATION=[redacted]`,
    `PASSWORD=${pw:-hunter2default}` → `PASSWORD=[redacted]`.
    `secret=` with nothing after it is not a match.
20. **keyed-colon-value** — a whole line, case-SENSITIVE shape: optional
    indent, then a key that is EITHER all-lowercase
    (`[a-z0-9_-]*<key word>[a-z0-9_-]*`, first char a lowercase letter)
    OR all-caps (`[A-Z0-9_-]*<KEY WORD>[A-Z0-9_-]*`, first char an
    uppercase letter), then `:` followed by at least one space or tab,
    then the rest of the line (first char non-space). Keep up to and
    including `: `. The key `authorization` alone is excluded (family 16
    owns it). Mixed-case keys never match here — `Secrets: never…`,
    `db_Password: x` — and `password:nospace` (no space after the colon)
    does not either. Examples: `password: SuperSecret99` →
    `password: [redacted]`; `api_key: 'qu0ted'` → `api_key: [redacted]`
    (quotes go with the value); `  db_password: NestedVal99` inside a
    fenced yaml block → `  db_password: [redacted]`; `api-key: hyphenval99`
    → `api-key: [redacted]`; `auth: hunter2` → `auth: [redacted]`.
21. **keyed-titlecase-value** — note-style paste, a whole line: optional
    indent, EXACTLY one of `Secret Token Password Passwd Api-Key Api_Key
    ApiKey Private-Key Private_Key PrivateKey Credential Auth` (that
    capitalisation, nothing before or after the word), `:`, whitespace,
    then ONE non-space token and nothing else but trailing whitespace.
    `Password: hunter2` → `Password: [redacted]`; `Token: xyzSecret99` →
    `Token: [redacted]`. Multi-word prose survives:
    `Password: is stored in the vault`. Exemptions apply: `Token: 3600`
    stays, `Password: 123456` is redacted.

There is deliberately no generic "long random string" heuristic: commit
hashes, ids and paths pass untouched, and the keyed families carry that
duty instead.

## Must NOT be redacted

The pass leaves these byte-identical; redacting any of them is a bug in
the pass, not caution:

- Keys that merely contain a key word as a substring across the letter
  boundary: `author: rokib`, `AUTHOR=rokib`, `git_author: rokib`,
  `TOKENIZER=gpt2`, `MAX_TOKENS=auto`, `max_tokens: 4096`.
- Settings named by their last word: `secret_globs: [.env*]`,
  `credentials_file: config/app.ini`, `api_key_rotation: monthly`,
  `TOKEN_URL=https://auth.example.com/token`, `oauth_provider=google`,
  `token_reporting: true`, `token_reporting=false`,
  `auth_enabled = true`, `auth_timeout: 30`, `token_expiry_seconds: 3600`.
- Setting literals as values: `"token_type": "Bearer"`,
  `auth: required`, `AUTH_METHOD=oauth2`.
- Bare variable references: `password: ${DB_VALUE}`, `db-password: ${DB_VALUE}`.
- Prose with a mixed-case key word: `Secrets: never read them, even on
  request.`, `Password: is stored in the vault`, `The secretary approved
  the rollout schedule.`
- Unrelated colon lines and bare words: `risk-assessment: complete`,
  `retries: 30`, `task_queue_worker_settings_module`, `id: 12345`.
- Hashes, paths, hosts: `deadbeefcafe1234…`, `/usr/local/lib/app/module.py`,
  `db.example.com/app`, `core.windows.net`, a `-----BEGIN CERTIFICATE-----`
  mention in a sentence.

## Known gaps — the "when unsure, drop it" rule covers them

The families above do not catch: `Authorization: Digest …` or any scheme
other than Bearer/Basic/token; a bare lowercase `authorization: <value>`
line; `https://token@host` (userinfo without a colon); a hyphenated env
key (`API-KEY=…`); a colon form with no space after the colon. When a
drafted payload carries one of these, drop that paragraph and note
`[redacted]` rather than reasoning that it slipped the patterns.

## The check (yes/no) — `--check` equivalent

Some skills only need to know whether a payload is clean. Run the full
pass mentally and count real replacements (exempt matches do not count):

- Any count > 0 → **dirty**. Report only family names and counts
  (`would redact 2: aws-access-key-id (1), keyed-colon-value (1)`), never
  the matched text; then drop the doubtful paragraph and note `[redacted]`.
- Zero → **clean**. Text that already contains `[redacted]` is clean; an
  empty payload is clean.

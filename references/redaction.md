# Redaction reference

Every command output `/cfm:diagnose` shows in the transcript — a failing
test's message, a stack trace, a probe's log line — passes through this
pass first. It is the single source of the redaction
rules: apply it by hand, exactly as written, and send only the result.
Nothing else may carry a rule list of its own. The policy is DROP, not
truncate: a match becomes the literal text `[redacted]`, and no step of
the pass ever quotes the matched content back — not in a warning, not in
a count, not in a question to the user.

**What this pass is, and is not.** It operates only on output a command
has already produced. It takes no other input: nothing is looked up,
opened, or collected to feed it. Its one job is to make sure that a
secret a test or log happens to print is dropped before it enters the
transcript. It never forwards or stores one, and nothing is sent off the
machine.

**Used by:** `/cfm:diagnose`.

## Fail closed

If the pass cannot be completed — the output is too long to read in
full, a family cannot be applied with confidence — show NOTHING of that
output. Emit a one-line warning and continue. When unsure whether a
string is a secret, drop the whole paragraph and note `[redacted]`.
Never show the unredacted output "just this once".

## The pass, step by step

1. Capture the output in full before redacting anything.
2. Apply the families below **in the order listed** — whole blocks first,
   vendor-shaped strings, then headers and URLs, then the keyed-value
   forms last (quoted-JSON before colon forms). Later families see the
   earlier families' output, so a value already replaced is not matched
   again by a later family.
3. For every keyed-value match, run the exemption check before replacing.
   An exempt value stays byte-identical and is not counted.
4. Count each real replacement by family name.
5. Show only the redacted result. If any count is non-zero, follow it
   with `redacted N match(es): <family> (n), <family> (n)`.
6. The pass is idempotent: running it again on its output changes
   nothing. If a second pass would change something, the first was wrong
   — redo it.

## Key words

The keyed-value families match a key that **contains** one of these
words: `secret`, `token`, `password`, `passwd`, `api_key` (with or
without the underscore), `private_key` (with or without the underscore),
`credential`, `authorization`, `auth`.

- Matching is case-insensitive in the assignment and JSON forms.
- `token` and `auth` end at a letter boundary: the next character must
  not be a letter (any case). So `TOKENIZER`, `author`, `AUTHOR`,
  `git_author`, `MAX_TOKENS` are not keys; `authtoken`, `oauth_token`,
  `AUTHORIZATION`, `token_secret`, `AUTH_HEADER` still are.
- `secret` is open-ended: `secrets`, `client_secrets`, `db_secret_v2`
  all match.
- Colon forms additionally accept a hyphen inside `api-key` and
  `private-key`.

## Exemptions — apply to the keyed-value families only

A keyed match is left untouched when the **whole value** (trailing
whitespace ignored) is one of:

1. `[redacted]` already.
2. `true`, `false`, `null` (any case).
3. A setting literal (any case):
   `required optional none null enabled disabled yes no on off basic
   bearer digest oauth oauth2 jwt hmac hs256 hs384 hs512 rs256 rs384
   rs512`.
4. A plain number (`30`, `3600`, `1.5`) — UNLESS the key contains
   `password`, `passwd` or `pin` (any case): a numeric password or PIN
   is redacted.
5. **Assignment and colon forms only:** the key's last word (the part
   after the final `_`, `.` or `-`, or the whole key) says the value is a
   location, a name, a policy or a setting:

   ```
   glob globs file files path dir url uri provider type name rotation
   ttl expir* length prefix scheme issuer audience alg algorithm
   reporting enabled required timeout count limit method mode source
   version
   ```

   So `secret_globs: [...]`, `api_key_rotation: monthly`,
   `oauth_provider=google`, `token_reporting=false`, `auth_timeout: 30`
   are untouched. `header` is deliberately NOT in the list, so a key
   ending in `_HEADER` is redacted. This suffix rule does not apply to
   the quoted-JSON form; only exemptions 1–5 apply there
   (`"token_type": "Bearer"` stays).

Exemptions are anchored to the whole value, never the line: a value that
is a real secret followed by the text `[redacted]`, or followed by a
comment, is still redacted as a whole.

## Pattern families, in application order

Replacement is `[redacted]` for the entire match unless a family says
what it keeps. Vendor-shaped strings are described by their documented
form; apply the vendor's current fixed prefix and length, which you
know, rather than guessing from the look of a string.

1. **pem-block** — a PEM `BEGIN` marker line through the first matching
   `END` marker line, across lines, inclusive. Drop the whole block.
2. **pem-block-truncated** — a PEM `BEGIN` marker with no `END`, when
   EITHER the label names a private key, OR one of the next two lines
   starts (after optional whitespace) with 40 or more base64 characters.
   Drop from the marker to the END OF THE OUTPUT. A sentence that
   merely mentions a certificate marker, followed by ordinary prose,
   survives.
3. **jwt** — three base64url segments separated by dots, the first
   beginning with the JSON-header prefix every JWT shares, each segment
   at least 10, 10 and 5 characters long.
4. **jwt-partial** — the first two segments of the same shape, when the
   second also begins with the JSON prefix (a header-and-payload paste
   with the signature cut off).
5. **aws-access-key-id** — a 20-character upper-case alphanumeric id
   that begins with one of the four-letter prefixes AWS documents for
   access keys (long-term, temporary, group, user, role, and the other
   principal types). No word boundary: the first 20 characters of a
   longer run are dropped.
6. **gitlab-token** — a GitLab personal access token by its documented
   prefix and a run of 20 or more token characters.
7. **npm-token** — an npm access token by its documented prefix and
   36 alphanumerics.
8. **slack-webhook** — a Slack incoming-webhook URL (the vendor's
   webhook host with its three-part services path). The whole URL is
   dropped.
9. **slack-app-token** — a Slack app-level token by its documented
   prefix, a single digit, and a run of 10 or more token characters.
10. **azure-connection-key** — in an Azure connection string, case-
    insensitive, at a word boundary: the account-key, shared-access-key,
    shared-access-signature or short signature field name, then `=`,
    then a value up to the next `;` or whitespace. Keep the name and
    `=`, drop the value. An account name and the endpoint suffix
    survive.
11. **secret-key-token** — the two-letter `sk` prefix followed by a
    hyphen or underscore and a run of 20 or more token characters, not
    preceded by a letter or digit (so a word that merely ends in those
    two letters, such as `desk_`, is not one). This is the shape several
    API vendors use for their secret keys.
12. **slack-token** — a Slack bot, user or workspace token by its
    documented three-letter prefix, a type letter, a hyphen, and a run
    of 10 or more token characters.
13. **github-token** — a GitHub classic personal access token, OAuth
    token, or app token by its documented prefix (two letters, a type
    letter, an underscore) and 36 alphanumerics.
14. **github-fine-grained-pat** — a GitHub fine-grained personal access
    token by its documented longer prefix and a run of 22 or more token
    characters.
15. **google-api-key** — a Google API key by its documented four-letter
    prefix and 35 further key characters.
16. **authorization-header** — case-insensitive: the `Authorization`
    header name, a colon, the scheme word `Bearer`, `Basic` or `token`,
    whitespace, then a non-space run. Keep the header name and scheme,
    drop the run. An already-redacted header is left alone.
17. **url-credentials** — a URL whose authority carries a user name, a
    colon, and a password before `@`. Keep the scheme and everything
    after `@`, drop the user-and-password part as a unit, so the result
    reads `<scheme>://[redacted]@<host>...`. The user name goes too.
18. **keyed-json-value** — anywhere on a line, case-insensitive: a
    quoted key (`"` or `'`) that contains a key word, optional spaces,
    `:`, optional spaces, a quoted value (same or other quote, escapes
    allowed, no newline). Keep the key and the quotes, replace the value,
    so the result reads `"password": "[redacted]"`. Works inside a
    one-line object. Unquoted JSON values (a number, `null`) are not
    matched.
19. **keyed-assignment-value** — a whole line, case-insensitive:
    optional indent, an optional leading shell keyword that marks a
    variable for child processes, a key made of letters, digits and
    underscores that contains a key word (no hyphens), optional spaces,
    `=`, optional spaces, then the rest of the line (first char
    non-space). The whole remainder is the value, trailing comment
    included. Keep up to and including `=`; the key stays, the value
    becomes `[redacted]`. A key with nothing after `=` is not a match.
20. **keyed-colon-value** — a whole line, case-SENSITIVE shape: optional
    indent, then a key that is EITHER all-lowercase (letters, digits,
    `_`, `-`; first char a lowercase letter) OR all-caps (same set with
    upper-case letters; first char an uppercase letter), containing a
    key word, then `:` followed by at least one space or tab, then the
    rest of the line (first char non-space). Keep up to and including
    `: `, so the result reads `password: [redacted]`. Quotes around the
    value go with the value. The key `authorization` alone is excluded
    (family 16 owns it). Mixed-case keys never match here, and a colon
    with no space after it does not either. An indented key inside a
    fenced yaml block matches like any other line.
21. **keyed-titlecase-value** — note-style paste, a whole line: optional
    indent, EXACTLY one of `Secret Token Password Passwd Api-Key Api_Key
    ApiKey Private-Key Private_Key PrivateKey Credential Auth` (that
    capitalisation, nothing before or after the word), `:`, whitespace,
    then ONE non-space token and nothing else but trailing whitespace.
    The result reads `Password: [redacted]`. Multi-word prose survives:
    `Password: is stored in the vault`. Exemptions apply: `Token: 3600`
    stays, a numeric password is redacted.

There is deliberately no generic "long random string" heuristic: commit
hashes, ids and paths pass untouched, and the keyed families carry that
duty instead.

## Must NOT be redacted

The pass leaves these byte-identical; redacting any of them is a bug in
the pass, not caution:

- Keys that merely contain a key word as a substring across the letter
  boundary: `author: rokib`, `git_author: rokib`, `max_tokens: 4096`,
  and their upper-case assignment forms (an author name, a tokenizer
  name, a maximum token count).
- Settings named by their last word: `secret_globs: [...]`,
  `api_key_rotation: monthly`, a token endpoint URL under a key ending
  in `_url`, `oauth_provider: google`, `token_reporting: true`,
  `auth_enabled: true`, `auth_timeout: 30`, `token_expiry_seconds: 3600`.
- Setting literals as values: `"token_type": "Bearer"`,
  `auth: required`, `auth_method: oauth2`.
- Prose with a mixed-case key word: `Secrets: never read them, even on
  request.`, `Password: is stored in the vault`, `The secretary approved
  the rollout schedule.`
- Unrelated colon lines and bare words: `risk-assessment: complete`,
  `retries: 30`, `task_queue_worker_settings_module`, `id: 12345`.
- Hashes, paths, hosts: a commit hash, `/usr/local/lib/app/module.py`,
  `db.example.com/app`, a cloud endpoint suffix, a certificate marker
  mentioned in a sentence.

## Known gaps — the "when unsure, drop it" rule covers them

The families above do not catch: an `Authorization` header with the
`Digest` scheme or any scheme other than Bearer, Basic or token; a bare
lowercase `authorization: <value>` line; a URL whose authority carries a
user name without a password; a hyphenated assignment key; a colon form
with no space after the colon. When the output carries one of
these, drop that paragraph and note `[redacted]` rather than reasoning
that it slipped the rules.

## The check (yes/no)

Some skills only need to know whether an output is clean. Run the full
pass mentally and count real replacements (exempt matches do not count):

- Any count > 0 → **dirty**. Report only family names and counts
  (`would redact 2: aws-access-key-id (1), keyed-colon-value (1)`), never
  the matched text; then drop the doubtful paragraph and note `[redacted]`.
- Zero → **clean**. Text that already contains `[redacted]` is clean; an
  empty output is clean.

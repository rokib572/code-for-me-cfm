#!/usr/bin/env python3
"""Redaction filter for anything leaving the repo (tracker comments, ticket
bodies, phase-gate notes). Reads stdin, writes redacted stdout.

THE single source of redaction patterns. Skills and CONNECTORS.md point
here; nothing else may duplicate this list (that duplication is exactly
the drift class cfm exists to kill).

Policy: DROP the match — replace with [redacted] — never truncate.
No mode and no error path ever prints matched content. Output is stable
under re-redaction: --check exits 0 on already-redacted text.
"""
import argparse
import re
import sys

# `token` and `auth` end at a letter boundary so TOKENIZER, AUTHOR and
# oauth_provider are not keys (authtoken, oauth_token and AUTHORIZATION=
# still are); `secret` stays open-ended (secrets, client_secrets)
_KEY = (r"(?:secret|token(?![a-z])|password|passwd|api_?key|private_?key"
        r"|credential|authorization|auth(?![a-z]))")
# colon-form variants: hyphen-aware (k8s/helm keys), plus the Title-case
# exact-word set for note-style pastes ("Password: hunter2")
_KEY_COLON = (r"(?:secret|token(?![a-z])|password|passwd|api[-_]?key"
              r"|private[-_]?key|credential|authorization|auth(?![a-z]))")
_KEY_COLON_UPPER = (r"(?:SECRET|TOKEN(?![A-Z])|PASSWORD|PASSWD|API[-_]?KEY"
                    r"|PRIVATE[-_]?KEY|CREDENTIAL|AUTHORIZATION|AUTH(?![A-Z]))")
_KEY_TITLE = (r"(?:Secret|Token|Password|Passwd|Api[-_]?Key|Private[-_]?Key"
              r"|Credential|Auth)")
# a key whose LAST word says the value is a location, a name, a policy or a
# setting — never the credential itself (secret_globs, credentials_file,
# token_url, api_key_rotation). Not `header`: AUTH_HEADER=Basic ... leaks.
_KEY_META_SUFFIX = re.compile(
    r"(?i)(?:^|[_.-])(?:globs?|files?|path|dir|url|uri|provider|type|name"
    r"|rotation|ttl|expir[a-z]*|length|prefix|scheme|issuer|audience"
    r"|alg|algorithm|reporting|enabled|required|timeout|count|limit"
    r"|method|mode|source|version)$")
_KEY_NAME = re.compile(r"([A-Za-z0-9_.-]+)[ \t]*[=:]")
# literal values that are a setting, not a credential
_META_VALUE = re.compile(
    r"(?i:required|optional|none|null|enabled|disabled|yes|no|on|off|basic"
    r"|bearer|digest|oauth2?|jwt|hmac|[hr]s(?:256|384|512))[ \t]*")


def _drop(match):
    return "[redacted]"


def _url_repl(match):
    # keep scheme + host so the reference stays useful; drop only user:pass@
    return match.group("scheme") + "[redacted]@"


def _auth_header_repl(match):
    # keep "Authorization: <scheme>"; drop the credential
    return match.group(1) + " [redacted]"


def _keyed_exempt(key, value):
    """Values that are plainly not credentials — anchored to the WHOLE
    value, never the line. Numbers stay exempt unless the key smells like
    a password/PIN."""
    if re.fullmatch(r"\[redacted\][ \t]*", value):
        return True
    if re.fullmatch(r"(?i:true|false|null)[ \t]*", value):
        return True
    if _META_VALUE.fullmatch(value):
        return True
    name = _KEY_NAME.search(key)
    if name and _KEY_META_SUFFIX.search(name.group(1)):
        return True
    # bare variable reference only — ${VAR}; defaults like ${x:-y} are values
    if re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}[ \t]*", value):
        return True
    return (re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[ \t]*", value) is not None
            and re.search(r"(?i)password|passwd|pin", key) is None)


def _keyed_repl(match):
    if _keyed_exempt(match.group(1), match.group(2)):
        return match.group(0)
    return match.group(1) + "[redacted]"


def _keyed_json_repl(match):
    q = match.group("vq")
    value = match.group(0)[len(match.group(1)):]
    if _keyed_exempt(match.group(1), value.strip(q)):
        return match.group(0)
    return match.group(1) + q + "[redacted]" + q


# (name, compiled regex, replacer) — applied in order: whole blocks first,
# keyed-value forms last (json before colon so JSON lines are consumed
# first). The generic long-token heuristic is deliberately absent (too many
# false positives on hashes/ids); keyed values carry that duty instead.
PATTERNS = [
    ("pem-block",
     re.compile(r"-----BEGIN [A-Z0-9 ]*-----.*?-----END [A-Z0-9 ]*-----", re.S),
     _drop),
    # truncated block (no END): only when the label says PRIVATE KEY, or a
    # base64-ish body line follows within 2 lines — prose mentions survive
    ("pem-block-truncated",
     re.compile(r"-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY[A-Z0-9 ]*-----"
                r"|[A-Z0-9 ]*-----"
                r"(?=(?:[^\n]*\n){1,2}[ \t]*[A-Za-z0-9+/=]{40,}))"
                r".*", re.S),
     _drop),
    ("jwt",
     re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
     _drop),
    ("jwt-partial",
     re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{7,}"),
     _drop),
    ("aws-access-key-id",
     re.compile(r"(?:A3T[A-Z0-9]|AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)"
                r"[0-9A-Z]{16}"),
     _drop),
    ("gitlab-token",
     re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
     _drop),
    ("npm-token",
     re.compile(r"npm_[A-Za-z0-9]{36}"),
     _drop),
    ("slack-webhook",
     re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/"
                r"B[A-Za-z0-9_]+/[A-Za-z0-9_]+"),
     _drop),
    ("slack-app-token",
     re.compile(r"xapp-[0-9]-[A-Za-z0-9-]{10,}"),
     _drop),
    ("azure-connection-key",
     re.compile(r"(?i)\b((?:AccountKey|SharedAccessKey|SharedAccessSignature"
                r"|sig)=)(?!\[redacted\])[^;\s]+"),
     lambda m: m.group(1) + "[redacted]"),
    ("secret-key-token",
     re.compile(r"(?<![A-Za-z0-9])sk[-_][A-Za-z0-9_-]{20,}"),
     _drop),
    ("slack-token",
     re.compile(r"xox[a-z]-[A-Za-z0-9-]{10,}"),
     _drop),
    ("github-token",
     re.compile(r"gh[pousr]_[A-Za-z0-9]{36}"),
     _drop),
    ("github-fine-grained-pat",
     re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
     _drop),
    ("google-api-key",
     re.compile(r"AIza[0-9A-Za-z_-]{35}"),
     _drop),
    ("authorization-header",
     re.compile(r"(?i)\b(Authorization[ \t]*:[ \t]*(?:Bearer|Basic|token))"
                r"[ \t]+(?!\[redacted\](?:[ \t]|$))\S+"),
     _auth_header_repl),
    ("url-credentials",
     re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^@\s]+@"),
     _url_repl),
    ("keyed-json-value",
     re.compile(r'(?i)((?P<kq>["\'])[A-Za-z0-9_.-]*' + _KEY
                + r'[A-Za-z0-9_.-]*(?P=kq)[ \t]*:[ \t]*)(?P<vq>["\'])'
                + r'(?!\[redacted\](?P=vq))(?:(?!(?P=vq))[^\\\n]|\\.)*(?P=vq)'),
     _keyed_json_repl),
    ("keyed-env-value",
     re.compile(r"(?im)^([ \t]*(?:export[ \t]+)?[A-Za-z0-9_]*" + _KEY
                + r"[A-Za-z0-9_]*[ \t]*=[ \t]*)(\S[^\n]*)$"),
     _keyed_repl),
    # colon form takes config-shaped keys only: all-lowercase or ALL-CAPS
    # (prose like "Secrets: never..." is mixed-case and excluded); the
    # authorization key belongs to the authorization-header pattern
    ("keyed-colon-value",
     re.compile(r"(?m)^([ \t]*(?!(?i:authorization)[ \t]*:)"
                r"(?:(?=[a-z])[a-z0-9_-]*" + _KEY_COLON + r"[a-z0-9_-]*"
                r"|(?=[A-Z])[A-Z0-9_-]*" + _KEY_COLON_UPPER + r"[A-Z0-9_-]*)"
                r"[ \t]*:[ \t]+)(\S[^\n]*)$"),
     _keyed_repl),
    # note-style paste: Capitalized EXACT key word with a SINGLE-token value
    # ("Password: hunter2"); multi-word prose after the colon survives
    ("keyed-titlecase-value",
     re.compile(r"(?m)^([ \t]*" + _KEY_TITLE + r"[ \t]*:[ \t]+)"
                r"(\S+)[ \t]*$"),
     _keyed_repl),
]


def redact(text):
    """Return (redacted_text, [(pattern_name, count), ...]). Counts only
    real replacements — exempt keyed values return the match unchanged and
    are not counted, so --check stays honest."""
    counts = []
    for name, regex, repl in PATTERNS:
        n = 0

        def wrapper(match, repl=repl):
            nonlocal n
            out = repl(match)
            if out != match.group(0):
                n += 1
            return out

        text = regex.sub(wrapper, text)
        if n:
            counts.append((name, n))
    return text, counts


def main():
    parser = argparse.ArgumentParser(
        description="cfm redaction filter: stdin -> redacted stdout.")
    parser.add_argument(
        "--check", action="store_true",
        help="exit 1 if anything would be redacted (pattern names on stderr,"
             " never the matched text); exit 0 if clean")
    args = parser.parse_args()

    text = sys.stdin.read()
    redacted, counts = redact(text)

    if args.check:
        if counts:
            total = sum(n for _, n in counts)
            names = ", ".join(f"{name} ({n})" for name, n in counts)
            print(f"redact --check: {total} match(es) would be redacted:"
                  f" {names}", file=sys.stderr)
            return 1
        return 0

    sys.stdout.write(redacted)
    return 0


if __name__ == "__main__":
    sys.exit(main())

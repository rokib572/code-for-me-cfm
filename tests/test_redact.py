"""The redaction filter: every pattern class drops its secret with
[redacted] (never a truncation), keyed values keep the key, and clean dev
text passes byte-identical."""

from __future__ import annotations

import subprocess
import sys
import unittest

from helpers import script

REDACT = script("redact.py")


def run(text, *args):
    return subprocess.run([sys.executable, REDACT, *args], input=text,
                          capture_output=True, text=True)


def redact(text):
    return run(text).stdout


class PatternClasses(unittest.TestCase):
    SECRETS = {
        "pem-block": "-----BEGIN RSA PRIVATE KEY-----\nEXAMPLEBODYxxxxxxxxxxxxx\n"
                     "EXAMPLEBODYxxxxxxxxx\n-----END RSA PRIVATE KEY-----",
        "aws-access-key-id": "AKIAEXAMPLEXXXXXXXXX",
        "secret-key-token": "sk-EXAMPLExxxxxxxxxxxxxxx",
        "slack-token": "xoxb-EXAMPLE-xxxxxxxx",
        "github-token": "ghp_EXAMPLExxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "github-fine-grained-pat": "github_pat_EXAMPLE_xxxxxxxxxxxxxxxx",
        "jwt": "eyJEXAMPLExxxxxx.eyJEXAMPLExxxxxx.EXAMPLExxxx",
        "jwt-partial": "eyJEXAMPLEyyyyyy.eyJEXAMPLEyyyy",
        "secret-key-underscore": "sk_live_EXAMPLExxxxxxxxxxxxxxx",
        "github-oauth-token": "gho_EXAMPLExxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "google-api-key": "AIzaEXAMPLExxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "aws-temporary-key": "ASIAEXAMPLEXXXXXXXXX",
        "gitlab-token": "glpat-EXAMPLExxxxxxxxxxxxxxx",
        "npm-token": "npm_EXAMPLExxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "slack-webhook": "https://hooks.slack.com/services/TEXAMPLE/BEXAMPLE/EXAMPLExxxxxxxxx",
        "slack-app-token": "xapp-1-EXAMPLE-xxxxxxxx",
    }

    def test_every_class_drops_whole(self):
        for name, secret in self.SECRETS.items():
            out = redact(f"before {secret} after")
            self.assertIn("[redacted]", out, name)
            self.assertFalse(any(secret[i:i + 6] in out for i in range(len(secret) - 5)),
                             f"{name}: a 6-char substring survived")
            self.assertIn("before", out); self.assertIn("after", out)

    def test_azure_connection_key(self):
        out = redact("DefaultEndpointsProtocol=https;AccountName=x;AccountKey=EXAMPLEKEYxxxxxxxxxxx==;EndpointSuffix=core.windows.net\n")
        self.assertNotIn("EXAMPLEKEY", out)
        self.assertIn("AccountKey=[redacted]", out)
        self.assertIn("AccountName=x", out); self.assertIn("core.windows.net", out)

    def test_url_credentials(self):
        out = redact("db: postgres://user:hunter2pass@db.example.com/app\n")
        self.assertNotIn("hunter2", out); self.assertNotIn("user:", out)
        self.assertIn("postgres://[redacted]@db.example.com/app", out)

    def test_keyed_values(self):
        out = redact('API_KEY=abc123def456\n"password": "hunter2"\n')
        self.assertIn("API_KEY=", out); self.assertNotIn("abc123", out)
        self.assertIn('"password"', out); self.assertNotIn("hunter2", out)
        self.assertEqual(out.count("[redacted]"), 2)

    def test_truncated_pem(self):
        out = redact("before text\n-----BEGIN RSA PRIVATE KEY-----\nTRUNCEXAMPLEBODYAAAABBBB\nTRUNCEXAMPLEBODYCCCC")
        self.assertIn("before text", out)
        self.assertNotIn("TRUNCEXAMPLE", out); self.assertNotIn("BEGIN RSA", out)
        self.assertIn("[redacted]", out)

    def test_truncated_pem_prose_survives(self):
        text = "Do not paste -----BEGIN CERTIFICATE----- blocks into tickets.\nOrdinary text follows.\n"
        self.assertEqual(redact(text), text)

    def test_auth_headers(self):
        out = redact("Authorization: Bearer EXAMPLE_BEARER_xxxx\nAuthorization: Basic EXAMPLExxxxxxxxxxxxxxxx=\n")
        self.assertIn("Authorization: Bearer [redacted]", out)
        self.assertIn("Authorization: Basic [redacted]", out)
        self.assertNotIn("EXAMPLE_BEARER_xxxx", out); self.assertNotIn("EXAMPLExxxx", out)

    def test_yaml_colon_forms(self):
        out = redact("password: SuperSecret99\napi_key: 'qu0ted'\n```yaml\nnested:\n"
                     "  db_password: NestedVal99\n```\n'password': 'fakepw99'\n")
        for gone in ("SuperSecret99", "qu0ted", "NestedVal99", "fakepw99"):
            self.assertNotIn(gone, out)
        for kept in ("password:", "api_key:", "  db_password:", "nested:", "```yaml",
                     "'password': '[redacted]'"):
            self.assertIn(kept, out)
        self.assertEqual(out.count("[redacted]"), 4)


class FalsePositives(unittest.TestCase):
    CLEAN = (
        "token_reporting: true\ntoken_reporting=false\nauth_enabled = true\n"
        "password: ${DB_VALUE}\nretries: 30\nauth_timeout: 30\ntoken_expiry_seconds: 3600\n"
        "max_tokens: 4096\ntask_queue_worker_settings_module\n"
        "Secrets: never read them, even on request.\nPassword: is stored in the vault\n"
        "risk-assessment: complete\n"
        # substring keys: author, oauth_provider, TOKENIZER are not credentials
        "author: rokib\nAUTHOR=rokib\ngit_author: rokib\noauth_provider=google\n"
        "TOKENIZER=gpt2\nMAX_TOKENS=auto\n"
        # a key whose last word says the value is a location, name or setting
        "secret_globs: [.env*]\ncredentials_file: config/app.ini\n"
        "api_key_rotation: monthly\nTOKEN_URL=https://auth.example.com/token\n"
        '"token_type": "Bearer"\nauth: required\nAUTH_METHOD=oauth2\n'
    )

    def test_guard_lines_byte_identical(self):
        self.assertEqual(redact(self.CLEAN), self.CLEAN)

    def test_clean_dev_text(self):
        text = ("Deployed commit deadbeefcafe1234deadbeefcafe1234deadbeef to staging.\n"
                "See /usr/local/lib/app/module.py and the record with id: 12345.\n"
                "The secretary approved the rollout schedule.\n")
        self.assertEqual(redact(text), text)

    def test_boundaries_do_not_open_leaks(self):
        # the boundary that spares TOKENIZER must not spare authtoken,
        # AUTHORIZATION= or oauth_token
        for text, kept in (("authtoken=abc123secret\n", "authtoken=[redacted]"),
                           ("AUTHORIZATION=Bearer abcdef\n", "AUTHORIZATION=[redacted]"),
                           ("oauth_token=abcdef\n", "oauth_token=[redacted]"),
                           ("client_secret=abcdef\n", "client_secret=[redacted]"),
                           ("AUTH_HEADER=Basic abcdef\n", "AUTH_HEADER=[redacted]"),
                           ("auth: hunter2\n", "auth: [redacted]"),
                           ('"token_secret": "abcdef"\n', '"token_secret": "[redacted]"')):
            out = redact(text)
            self.assertIn(kept, out, text)
            self.assertNotIn("abc", out, text)
            self.assertNotIn("hunter2", out, text)


class Boundaries(unittest.TestCase):
    def test_marker_adjacent_value_still_redacted(self):
        for text, gone, kept in (("password: hunter2 [redacted]\n", "hunter2", "password: [redacted]"),
                                 ("PASSWORD=realLeak42  # will be [redacted] in the ticket\n",
                                  "realLeak42", "PASSWORD=[redacted]")):
            out = redact(text)
            self.assertNotIn(gone, out); self.assertIn(kept, out)
            self.assertEqual(run(text, "--check").returncode, 1)

    def test_value_boundaries(self):
        out = redact('"password": "it\'sSecret77"\n')
        self.assertNotIn("sSecret77", out); self.assertIn('"password": "[redacted]"', out)
        out = redact("PASSWORD=${pw:-hunter2default}\n")
        self.assertNotIn("hunter2default", out); self.assertIn("PASSWORD=[redacted]", out)
        self.assertIn("password: ${DB_VALUE}", redact("password: ${DB_VALUE}\n"))
        out = redact("password: 123456\nAPI_PIN_PASSWORD=8675309\n")
        self.assertNotIn("123456", out); self.assertNotIn("8675309", out)
        self.assertIn("token_expiry_seconds: 3600", redact("token_expiry_seconds: 3600\n"))

    def test_titlecase_and_hyphen_keys(self):
        for text, gone, kept in (("Password: hunter2\n", "hunter2", "Password: [redacted]"),
                                 ("Token: xyzSecret99\n", "xyzSecret99", "Token: [redacted]"),
                                 ("api-key: hyphenval99\n", "hyphenval99", "api-key: [redacted]")):
            out = redact(text)
            self.assertNotIn(gone, out); self.assertIn(kept, out)
        for text in ("Secrets: never read them, even on request.\n", "Password: is stored in the vault\n",
                     "db-password: ${DB_VALUE}\n", "risk-assessment: complete\n"):
            self.assertEqual(redact(text), text)

    def test_idempotent_and_check_mode(self):
        doc = ("password: hunter2 [redacted]\nPASSWORD=realLeak42  # will be [redacted] in the ticket\n"
               '"password": "it\'sSecret77"\nPASSWORD=${pw:-hunter2default}\npassword: 123456\n'
               "API_PIN_PASSWORD=8675309\nAuthorization: Bearer EXAMPLE_BEARER_yyyy\n"
               "Authorization: Basic EXAMPLExxxxxxxxxxxxxxxx=\n"
               "db: postgres://user:hunter2pass@db.example.com/app\ntask_queue_worker_settings_module\n"
               "Secrets: never read them, even on request.\ntoken_expiry_seconds: 3600\n"
               "-----BEGIN RSA PRIVATE KEY-----\nTRUNCEXAMPLEBODY\n")
        one = redact(doc); two = redact(one); three = redact(two)
        self.assertTrue(one == two == three)
        self.assertEqual(run(one, "--check").returncode, 0)
        self.assertEqual(run(doc, "--check").returncode, 1)
        p = run("key AKIAEXAMPLEXXXXXXXXX end", "--check")
        self.assertEqual(p.returncode, 1)
        self.assertIn("aws-access-key-id", p.stderr)
        self.assertNotIn("AKIAEX", p.stderr + p.stdout)
        self.assertEqual(run("nothing secretive here, just prose\n", "--check").returncode, 0)

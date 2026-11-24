"""PII handling for anything this tool writes to disk.

Invoices are full of other people's personal data: names, street addresses,
phone numbers, gate codes. The tool needs almost none of it. The rules:

1. Don't collect it. The extraction schema has no address/phone/email fields.
2. Scrub free text anyway, in case the model copies some into a description.
3. Pseudonymize customer names in saved reports and logs. Only the email to
   payroll (who already has this data) shows the real last name.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"), "[phone]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[card]"),
    (
        re.compile(
            r"\b\d{1,6}\s+(?:[A-Z][a-z]+\s){1,3}"
            r"(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Ln|Lane|Ct|Court|Blvd|Way|Cir|Circle|Pl|Place|Ter|Trl)\b\.?",
        ),
        "[address]",
    ),
    (re.compile(r"\b(?:gate|lock|alarm|door)\s*code\s*[:#]?\s*\w+", re.I), "[access code]"),
]


def scrub_text(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _key() -> bytes:
    # A local secret so pseudonyms can't be reversed by guessing common names.
    # Set PAYROLL_AUDIT_PSEUDONYM_KEY in your environment; never commit it.
    return os.environ.get("PAYROLL_AUDIT_PSEUDONYM_KEY", "dev-only-not-secret").encode()


def pseudonymize(name: str) -> str:
    digest = hmac.new(_key(), name.strip().lower().encode(), hashlib.sha256).hexdigest()
    return f"cust_{digest[:8]}"

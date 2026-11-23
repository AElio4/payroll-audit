"""Tamper-evident audit trail.

Each run appends one JSON line per finding to a log file. Every record carries
the SHA-256 of the previous record, so editing or deleting a past line breaks
the chain and `verify()` catches it. Records reference photos by hash and
customers by pseudonym, so the log itself holds no customer PII.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Finding
from .redact import pseudonymize

GENESIS = "0" * 64


def _hash(record: dict) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    lines = path.read_text().strip().splitlines()
    return json.loads(lines[-1])["hash"] if lines else GENESIS


def append(path: Path, findings: list[Finding], photo_hashes: list[str], run_id: str) -> None:
    prev = _last_hash(path)
    with path.open("a") as f:
        for finding in findings:
            e = finding.expected
            record = {
                "run_id": run_id,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": finding.kind,
                "customer": pseudonymize(finding.customer),
                "job_date": finding.job_date.isoformat(),
                "amount": finding.amount,
                "rule": finding.detail,
                # Paper trail: which job and line on the invoice produced this.
                "source_line": None if e is None else {
                    "job_index": e.job_index,
                    "item_index": e.item_index,
                    "category": e.category.value,
                    "written": e.source.value,
                },
                "stub_row_index": finding.stub_row_index,
                "photo_sha256": photo_hashes,
                "prev": prev,
            }
            record["hash"] = _hash(record)
            prev = record["hash"]
            f.write(json.dumps(record) + "\n")


def verify(path: Path) -> bool:
    prev = GENESIS
    for line in path.read_text().strip().splitlines():
        record = json.loads(line)
        claimed = record.pop("hash")
        if record["prev"] != prev or _hash(record) != claimed:
            return False
        prev = claimed
    return True

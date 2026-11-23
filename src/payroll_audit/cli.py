"""Command line entry point.

    # Offline, from JSON (no API key needed). This is what the tests use.
    python -m payroll_audit audit --jobs tests/fixtures/run2_jobs.json --stub tests/fixtures/run2_stub.json

    # From photos (needs ANTHROPIC_API_KEY in the environment).
    python -m payroll_audit run --invoices inv1.jpg inv2.jpg --stub stub.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from . import audit_log
from .audit import audit, missing_total
from .email_draft import draft_email
from .models import Finding, InvoiceExtraction, PayStub
from .rules import DEFAULT_RULES, PayRules


def stub_total_ok(stub: PayStub) -> bool:
    """Rows should add up to the printed total; if not, the photo was misread."""
    return abs(sum(r.gross_pay for r in stub.rows) - stub.grand_total) < 0.01


def report(inv: InvoiceExtraction, stub: PayStub, rules: PayRules) -> tuple[str, list[Finding], str | None]:
    findings = audit(inv.jobs, stub, rules)
    out: list[str] = []
    blocked: list[str] = []

    if inv.injection_suspected or stub.injection_suspected:
        blocked.append("text in a photo looked like instructions to the AI")
    if not stub_total_ok(stub):
        blocked.append(
            f"stub rows add up to ${sum(r.gross_pay for r in stub.rows):.2f} "
            f"but the printed total is ${stub.grand_total:.2f}"
        )

    out.append(f"Pay period {stub.period_start} to {stub.period_end}, stub total ${stub.grand_total:,.2f}")
    out.append(f"Policy: warranty_two_tech={rules.policy['warranty_two_tech']}, "
               f"tear_out_basis={rules.policy['tear_out_basis']}")
    out.append("")

    missing = [f for f in findings if f.kind == "missing"]
    out.append(f"MISSING ({len(missing)} items, ${missing_total(findings):,.2f})")
    for f in missing:
        e = f.expected
        out.append(f"  {f.customer} {f.job_date:%m/%d}  ${f.amount:,.2f}  {f.detail}  [{e.source.value} line {e.item_index + 1}]")

    extras = [f for f in findings if f.kind != "missing"]
    if extras:
        out.append("")
        out.append("FOR YOU ONLY (never sent to payroll)")
        for f in extras:
            out.append(f"  {f.kind:<11} {f.customer} {f.job_date:%m/%d}  ${f.amount:,.2f}  {f.detail}")

    email = None
    if blocked:
        out.append("")
        out.append("EMAIL NOT DRAFTED, needs a human look: " + "; ".join(blocked))
    else:
        email = draft_email(findings, rules)
    return "\n".join(out), findings, email


def _rules(args) -> PayRules:
    overrides = {}
    if args.warranty_two_tech:
        overrides["warranty_two_tech"] = args.warranty_two_tech
    if args.tear_out:
        overrides["tear_out_basis"] = args.tear_out
    return PayRules.load(args.rules, **overrides)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="payroll_audit")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("audit", "run"):
        s = sub.add_parser(name)
        s.add_argument("--rules", type=Path, default=DEFAULT_RULES)
        s.add_argument("--warranty-two-tech", choices=["each", "split"])
        s.add_argument("--tear-out", choices=["per_door", "per_job"])
        s.add_argument("--log", type=Path, help="append findings to a hash-chained audit log")
    sub.choices["audit"].add_argument("--jobs", type=Path, required=True)
    sub.choices["audit"].add_argument("--stub", type=Path, required=True)
    sub.choices["run"].add_argument("--invoices", type=Path, nargs="+", required=True)
    sub.choices["run"].add_argument("--stub", type=Path, nargs="+", required=True)
    v = sub.add_parser("verify-log")
    v.add_argument("log", type=Path)
    args = p.parse_args(argv)

    if args.cmd == "verify-log":
        ok = audit_log.verify(args.log)
        print("audit log OK" if ok else "audit log has been TAMPERED WITH")
        return 0 if ok else 1

    rules = _rules(args)
    hashes: list[str] = []
    if args.cmd == "audit":
        inv = InvoiceExtraction.model_validate(json.loads(args.jobs.read_text()))
        stub = PayStub.model_validate(json.loads(args.stub.read_text()))
    else:
        from .extract import extract_invoices, extract_stub

        inv, h1 = extract_invoices(args.invoices)
        stub, h2 = extract_stub(args.stub)
        hashes = h1 + h2

    text, findings, email = report(inv, stub, rules)
    print(text)
    if email:
        print("\n----- DRAFT EMAIL (review before sending) -----\n")
        print(email)
    if args.log:
        audit_log.append(args.log, findings, hashes, run_id=uuid.uuid4().hex[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())

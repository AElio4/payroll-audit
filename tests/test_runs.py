"""The two real pay periods this was built from, re-created with fake names."""

from conftest import load

from payroll_audit.audit import audit, missing_total
from payroll_audit.cli import report
from payroll_audit.email_draft import draft_email
from payroll_audit.rules import PayRules


def test_run1_finds_80_short(rules):
    inv, stub = load(1)
    findings = audit(inv.jobs, stub, rules)
    assert missing_total(findings) == 80
    missing = sorted((f.customer, f.amount) for f in findings if f.kind == "missing")
    assert missing == [("Brandt", 5), ("Brandt", 5), ("Brandt", 30), ("Hollis", 5), ("Okafor", 35)]


def test_run1_overpayment_is_never_in_the_email(rules):
    inv, stub = load(1)
    findings = audit(inv.jobs, stub, rules)
    assert any(f.kind == "overpaid" and f.customer == "Delacroix" for f in findings)
    email = draft_email(findings, rules)
    assert "Delacroix" not in email
    assert "Pryor" not in email          # $2.69 parts bonus is not flagged either


def test_run1_email_format(rules):
    inv, stub = load(1)
    email = draft_email(audit(inv.jobs, stub, rules), rules)
    assert email.startswith("Missing items")
    assert "Hollis 3/3\nwood door tear out 10 (2 man) --> $5" in email
    assert "Okafor 3/3\nwarranty $35" in email
    assert "2 man 1/2 $30" in email
    assert email.endswith("Total: $80")


def test_run1_open_questions_change_the_answer():
    inv, stub = load(1)
    strict = PayRules.load(warranty_two_tech="split", tear_out_basis="per_job")
    # Warranty drops to 17.50 and Brandt's two tear outs become one.
    assert missing_total(audit(inv.jobs, stub, strict)) == 80 - 17.5 - 5


def test_run2_finds_205_short(rules):
    inv, stub = load(2)
    assert stub.grand_total == 1630.69
    findings = audit(inv.jobs, stub, rules)
    assert missing_total(findings) == 205
    missing = {(f.customer, f.amount) for f in findings if f.kind == "missing"}
    assert missing == {("Marsh", 185), ("Reyes", 10), ("Lindqvist", 10)}


def test_run2_handwritten_lines_count(rules):
    inv, stub = load(2)
    findings = audit(inv.jobs, stub, rules)
    lindqvist = next(f for f in findings if f.customer == "Lindqvist")
    assert lindqvist.expected.source.value == "handwritten"


def test_report_blocks_email_when_stub_total_is_off(rules):
    inv, stub = load(2)
    stub.grand_total = 1700
    text, _, email = report(inv, stub, rules)
    assert email is None
    assert "EMAIL NOT DRAFTED" in text

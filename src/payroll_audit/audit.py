"""Compare what should have been paid against what the pay stub shows.

Pay stub rows don't name the item they pay for, only an amount per job. So we
match by amount within each job: every expected item looks for a paid row of
exactly the same amount. Whatever is left over on either side is a finding.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from .models import ExpectedPay, Finding, Job, PayStub
from .rules import PayRules, expected_pay


def _key(customer: str, job_date: date) -> tuple[str, date]:
    return customer.strip().lower(), job_date


def audit(jobs: list[Job], stub: PayStub, rules: PayRules) -> list[Finding]:
    expected = expected_pay(jobs, rules)

    # Group paid rows by job. Invoice number is the strongest key; jobs without
    # an invoice (e.g. a handwritten warranty call) fall back to name + date.
    rows_by_invoice: dict[str, list[int]] = defaultdict(list)
    rows_by_name: dict[tuple[str, date], list[int]] = defaultdict(list)
    for idx, row in enumerate(stub.rows):
        if row.invoice_id:
            rows_by_invoice[row.invoice_id].append(idx)
        rows_by_name[_key(row.customer, row.job_date)].append(idx)

    used: set[int] = set()
    findings: list[Finding] = []

    by_job: dict[int, list[ExpectedPay]] = defaultdict(list)
    for e in expected:
        by_job[e.job_index].append(e)

    for j_idx, job in enumerate(jobs):
        candidates = (
            rows_by_invoice.get(job.invoice_id or "", [])
            or rows_by_name.get(_key(job.customer, job.job_date), [])
        )
        open_rows = [i for i in candidates if i not in used]

        # Largest items first so a $185 door isn't "satisfied" by smaller rows.
        for e in sorted(by_job.get(j_idx, []), key=lambda e: -e.amount):
            match = next((i for i in open_rows if abs(stub.rows[i].gross_pay - e.amount) < 0.005), None)
            if match is not None:
                open_rows.remove(match)
                used.add(match)
            else:
                findings.append(
                    Finding(
                        kind="missing",
                        customer=job.customer,
                        job_date=job.job_date,
                        invoice_id=job.invoice_id,
                        amount=e.amount,
                        detail=e.rule,
                        expected=e,
                    )
                )

    # Paid rows nothing claimed: overpayment or a small extra. These are for
    # the installer's eyes only and never go in the payroll email.
    for idx, row in enumerate(stub.rows):
        if idx in used:
            continue
        small = 0 < row.gross_pay <= rules.policy["small_extra_max"]
        odd = round(row.gross_pay * 100) % 500 != 0
        note = " (odd amount, probably angle iron)" if odd and not small else ""
        findings.append(
            Finding(
                kind="small_extra" if small else "overpaid",
                customer=row.customer,
                job_date=row.job_date,
                invoice_id=row.invoice_id,
                amount=row.gross_pay,
                detail="paid row with no matching item" + (" (small extra, ignored)" if small else note),
                stub_row_index=idx,
            )
        )
    return findings


def missing_total(findings: list[Finding]) -> float:
    return round(sum(f.amount for f in findings if f.kind == "missing"), 2)

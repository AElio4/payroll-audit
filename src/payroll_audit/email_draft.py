"""Write the correction email in the same plain format I already send payroll.

Only "missing" findings go in. Overpayments and small extras are never
included: the email asks for what's owed, nothing else.
"""

from __future__ import annotations

from collections import OrderedDict

from .models import Finding
from .rules import PayRules


def _money(x: float) -> str:
    s = f"${x:,.2f}"
    return s[:-3] if s.endswith(".00") else s


def _line(f: Finding, rules: PayRules) -> str:
    e = f.expected
    assert e is not None
    label = rules.label(e.category)
    if e.category.value == "door":
        label = e.rule.split(" $")[0]          # e.g. "door 18' NWL"
    if e.category.value == "angle_iron":
        label = f"{label} ({e.rule.split(',')[0]})"   # e.g. "angle iron ($1/ft x 21 ft)"
    if rules.is_crew_rate(e.category):
        return f"{label} {_money(e.amount)}"
    if e.split:
        return f"{label} {e.job_amount:g} ({e.crew_size} man) --> {_money(e.amount)}"
    return f"{label} {_money(e.amount)}"


def draft_email(findings: list[Finding], rules: PayRules, signature: str = "") -> str | None:
    missing = [f for f in findings if f.kind == "missing" and f.expected is not None]
    if not missing:
        return None

    jobs: OrderedDict[tuple, list[Finding]] = OrderedDict()
    for f in sorted(missing, key=lambda f: (f.job_date, f.customer)):
        jobs.setdefault((f.customer, f.job_date), []).append(f)

    lines = ["Missing items", ""]
    for (customer, d), items in jobs.items():
        lines.append(f"{customer} {d.month}/{d.day}")
        lines.extend(_line(f, rules) for f in items)
        lines.append("")
    total = round(sum(f.amount for f in missing), 2)
    lines.append(f"Total: {_money(total)}")
    if signature:
        lines += ["", signature]
    return "\n".join(lines)

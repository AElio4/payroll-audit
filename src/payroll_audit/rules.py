"""Deterministic rules engine: turns extracted jobs into expected pay.

No LLM is involved here. Given the same jobs and the same pay_rules.toml, this
always produces the same numbers, which is what makes a finding defensible.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Category, ExpectedPay, Job, JobType, LineItem

DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "pay_rules.toml"


@dataclass
class PayRules:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: Path | str = DEFAULT_RULES, **policy_overrides: Any) -> "PayRules":
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        raw.setdefault("policy", {}).update(policy_overrides)
        return cls(raw)

    @property
    def policy(self) -> dict[str, Any]:
        return self.raw["policy"]

    def label(self, category: Category) -> str:
        item = self.raw["items"].get(category.value)
        if item:
            return item["label"]
        return {"door": "door", "rail": "rail", "buildout": "buildout"}.get(category.value, category.value)

    def is_crew_rate(self, category: Category) -> bool:
        return bool(self.raw["items"].get(category.value, {}).get("crew"))

    # -- pricing ---------------------------------------------------------

    def price(self, item: LineItem) -> tuple[float, str]:
        """Return (amount for the whole job, explanation) for one line item."""
        c = item.category
        if c is Category.door:
            return self._door(item)
        if c is Category.rail:
            return self._rail(item)
        if c is Category.buildout:
            return self._buildout(item)
        if c is Category.unknown:
            return 0.0, "not on the pay chart"

        rule = self.raw["items"][c.value]
        rate = float(rule["rate"])
        if rule.get("per") == "foot":
            feet = item.feet or 0
            return rate * feet, f"${rate:g}/ft x {feet:g} ft"  # label added by caller
        if rate == 0:
            return 0.0, f"{rule['label']} is unpaid"
        qty = item.quantity
        return rate * qty, f"{rule['label']} ${rate:g}" + (f" x {qty}" if qty > 1 else "")

    def _door(self, item: LineItem) -> tuple[float, str]:
        d = self.raw["door"]
        if item.width_ft is None:
            raise ValueError(f"door line '{item.description}' has no width")
        small = item.width_ft <= d["small_max_width_ft"]
        size = "small" if small else "large"
        load = "wind_load" if item.wind_load else "non_wind_load"
        rate = float(d[f"{size}_{load}"])
        tag = f"{item.width_ft:g}' {'WL' if item.wind_load else 'NWL'}"
        return rate * item.quantity, f"door {tag} ${rate:g}" + (f" x {item.quantity}" if item.quantity > 1 else "")

    def _rail(self, item: LineItem) -> tuple[float, str]:
        r = self.raw["rail"]
        if item.length_ft in r["paid_lengths_ft"]:
            return float(r["rate"]) * item.quantity, f"{item.length_ft:g}' rail ${r['rate']}"
        return 0.0, f"{item.length_ft:g}' rail is unpaid"

    def _buildout(self, item: LineItem) -> tuple[float, str]:
        b = self.raw["buildout"]
        small = (item.width_ft or 0) <= self.raw["door"]["small_max_width_ft"]
        rate = float(b["small" if small else "large"])
        return rate * item.quantity, f"buildout ${rate:g}"


def expected_pay(jobs: list[Job], rules: PayRules) -> list[ExpectedPay]:
    """Price every paid line item on every job, applying crew splits."""
    out: list[ExpectedPay] = []
    for j_idx, job in enumerate(jobs):
        for i_idx, item in enumerate(job.items):
            for unit_item, note in _expand(item, job, rules):
                job_amount, rule = rules.price(unit_item)
                if job_amount == 0:
                    continue
                split = _is_split(unit_item, job, rules)
                share = round(job_amount / job.crew_size, 2) if split else job_amount
                out.append(
                    ExpectedPay(
                        job_index=j_idx,
                        item_index=i_idx,
                        customer=job.customer,
                        job_date=job.job_date,
                        invoice_id=job.invoice_id,
                        category=unit_item.category,
                        description=item.description,
                        source=item.source,
                        rule=rule + note + (f", split {job.crew_size} ways" if split else ""),
                        job_amount=job_amount,
                        crew_size=job.crew_size,
                        split=split,
                        amount=share,
                    )
                )
    return out


def _expand(item: LineItem, job: Job, rules: PayRules):
    """Stub rows are one per pay item, so a qty-2 line becomes two units."""
    if item.category is Category.wood_disposal and item.quantity > 1:
        if rules.policy["tear_out_basis"] == "per_job":
            yield item.model_copy(update={"quantity": 1}), " (per job policy)"
            return
    if item.quantity > 1 and item.category is not Category.angle_iron:
        for _ in range(item.quantity):
            yield item.model_copy(update={"quantity": 1}), ""
        return
    yield item, ""


def _is_split(item: LineItem, job: Job, rules: PayRules) -> bool:
    if job.crew_size <= 1 or not rules.policy.get("split_evenly", True):
        return False
    if item.category is Category.warranty_call and job.job_type is JobType.warranty:
        return rules.policy["warranty_two_tech"] == "split"
    return True

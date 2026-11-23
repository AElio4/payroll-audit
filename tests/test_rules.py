from datetime import date

import pytest

from payroll_audit.models import Category, Job, JobType, LineItem
from payroll_audit.rules import PayRules, expected_pay


def door(width, wl):
    return LineItem(category=Category.door, description="door", width_ft=width, wind_load=wl)


@pytest.mark.parametrize(
    "width,wl,amount",
    [(12, False, 125), (12, True, 155), (16, False, 185), (18, True, 230), (9, False, 125)],
)
def test_door_base(rules, width, wl, amount):
    assert rules.price(door(width, wl))[0] == amount


def test_rails(rules):
    assert rules.price(LineItem(category=Category.rail, description="r", length_ft=12))[0] == 20
    assert rules.price(LineItem(category=Category.rail, description="r", length_ft=7))[0] == 0


def test_angle_iron_per_foot(rules):
    assert rules.price(LineItem(category=Category.angle_iron, description="+21 ft angle", feet=21))[0] == 21


@pytest.mark.parametrize(
    "cat", [Category.steel_disposal, Category.slide_lock, Category.warranty_upgrade,
            Category.reconnect_motor, Category.crew_1_half, Category.unknown],
)
def test_unpaid_items(rules, cat):
    assert rules.price(LineItem(category=cat, description="x"))[0] == 0


def _job(items, crew=2, jt=JobType.install):
    return Job(customer="Test", job_date=date(2026, 3, 1), crew_size=crew, job_type=jt, items=items)


def test_two_man_job_splits_everything(rules):
    job = _job([door(16, False),
                LineItem(category=Category.wood_disposal, description="tear out"),
                LineItem(category=Category.crew_2_half, description="2 man 1/2")])
    assert [e.amount for e in expected_pay([job], rules)] == [92.5, 5, 30]


def test_warranty_two_tech_policy():
    job = _job([LineItem(category=Category.warranty_call, description="w")], jt=JobType.warranty)
    assert expected_pay([job], PayRules.load(warranty_two_tech="each"))[0].amount == 35
    assert expected_pay([job], PayRules.load(warranty_two_tech="split"))[0].amount == 17.5


def test_tear_out_policy():
    job = _job([LineItem(category=Category.wood_disposal, description="t", quantity=2)], crew=1)
    assert [e.amount for e in expected_pay([job], PayRules.load(tear_out_basis="per_door"))] == [10, 10]
    assert [e.amount for e in expected_pay([job], PayRules.load(tear_out_basis="per_job"))] == [10]


def test_door_without_width_is_an_error(rules):
    with pytest.raises(ValueError):
        rules.price(LineItem(category=Category.door, description="door"))

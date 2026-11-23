import json
from pathlib import Path

import pytest

from payroll_audit.models import InvoiceExtraction, PayStub
from payroll_audit.rules import PayRules

FIXTURES = Path(__file__).parent / "fixtures"


def load(run: int):
    inv = InvoiceExtraction.model_validate(json.loads((FIXTURES / f"run{run}_jobs.json").read_text()))
    stub = PayStub.model_validate(json.loads((FIXTURES / f"run{run}_stub.json").read_text()))
    return inv, stub


@pytest.fixture
def rules():
    return PayRules.load()

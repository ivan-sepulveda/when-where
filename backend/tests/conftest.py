"""
Shared fixtures for the backend test suite.

`client` builds a FastAPI TestClient around the REAL app -- app/main.py
loads its data at import time straight from ../data/processed and
../data/reference (see app/data_loader.py's docstring), so importing
app.main here pulls in this repo's actual data, not a mock. That's
deliberate: this project's entire job is "read real data files and score
them," so test_main.py's job is to verify that pipeline end to end
against what's actually on disk right now. It's also what would have
caught the Namibia iso2-parsed-as-NaN bug that 500'd
/api/destinations/{country}/visa-requirements for every departure
country before this suite existed -- see
test_main.py::TestVisaRequirements for the regression tests that now
guard it.

test_data_loader.py, by contrast, builds small synthetic JSON fixtures
per test and monkeypatches app.data_loader's path constants -- those
tests are about the LOADER LOGIC (skip-on-bad-record behavior, name
normalization, the clustering algorithm), independent of what's
currently true of this repo's real reference data. test_scoring.py needs
no fixtures at all -- scoring.py is pure functions over plain
dicts/dates, no file I/O.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)

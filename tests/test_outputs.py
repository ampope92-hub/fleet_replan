"""Verifier for the line-haul pay run.

test.sh builds the agent's module from the shipped go.mod and the .go files it left, runs the
binary once on the month that shipped and once on a month it has never seen, and captures each
payroll.json root-only. The expected pay run is computed here, independently, in Python integers
from the same three input files, and the two are compared figure for figure.
"""

import hashlib
import json
import os
import pathlib

import pytest
from payroll_expected import expected

SHIPPED_RUN = pathlib.Path("/opt/run_shipped.json")
HOLDOUT_RUN = pathlib.Path("/opt/run_holdout.json")
SHIPPED_DATA = pathlib.Path("/opt/agent_data")
HOLDOUT_DATA = pathlib.Path("/opt/holdout")
GOMOD_CHECK = pathlib.Path("/opt/gomod_check.txt")

DRIVER_KEYS = ["driver_id", "runs", "cancellations", "paid_quarters", "driving_pence", "drop_pence",
               "distance_pence", "fuel_pence", "long_run_pence", "cancellation_pence", "total_pence"]
PENCE_PARTS = ["driving_pence", "drop_pence", "distance_pence", "fuel_pence", "long_run_pence",
               "cancellation_pence"]

# frozen at task-build time; the instruction says to leave the three files as shipped
SHIPPED_SHA = {
    "runs.csv": "8349b26fc1af8c1bb0c81abb6eb47f007f8af1802f4a5ba29a5cea4abd3677c2",
    "drivers.csv": "4b6c3806f34fe95dba1274e1efae2de579e33179bff5911e179e75aa5754fb7a",
    "tariff.json": "d0eef032bde4672f8c39d7fffc78060f92d1033022bed8cbd6281b3940df1ce7",
}

RUNS = [
    pytest.param(SHIPPED_RUN, SHIPPED_DATA, id="shipped"),
    pytest.param(HOLDOUT_RUN, HOLDOUT_DATA, id="holdout"),
]


def _open(path, mode="r"):
    return os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), mode)


def _load(path):
    assert path.exists() and path.stat().st_size > 0, (
        f"{path.name}: no payroll.json was written for this run"
    )
    with _open(path) as fh:
        text = fh.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        pytest.fail(f"{path.name}: not valid JSON ({e}): {text[:200]!r}")


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def test_go_mod_is_as_shipped():
    """go.mod comes back as issued; the module builds from the shipped copy either way."""
    assert GOMOD_CHECK.is_file() and GOMOD_CHECK.read_text().strip() == "ok", (
        "go.mod was changed; the instruction says to leave it alone"
    )


def test_shipped_export_unmodified():
    """The three files in /app/data come back byte for byte as issued."""
    for name, sha in SHIPPED_SHA.items():
        with _open(SHIPPED_DATA / name, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        assert got == sha, f"{name} was altered"


@pytest.mark.parametrize("run_path,data_dir", RUNS)
def test_report_shape(run_path, data_dir):
    """One object with drivers, unmatched_runs and total_pence; one entry per driver on the
    book, sorted by driver_id as text; every figure a whole number."""
    doc = _load(run_path)
    assert isinstance(doc, dict) and set(doc) == {"drivers", "unmatched_runs", "total_pence"}, (
        f"top-level keys must be drivers, unmatched_runs and total_pence, got "
        f"{sorted(doc) if isinstance(doc, dict) else type(doc).__name__}"
    )
    exp = expected(data_dir)
    ids = [d.get("driver_id") for d in doc["drivers"]]
    assert ids == [d["driver_id"] for d in exp["drivers"]], (
        "drivers must be exactly the drivers on the book, one each, sorted by driver_id as text"
    )
    for d in doc["drivers"]:
        assert set(d) == set(DRIVER_KEYS), f"{d.get('driver_id')}: keys must be {DRIVER_KEYS}"
        for k in DRIVER_KEYS[1:]:
            assert _whole(d[k]), f"{d['driver_id']}: {k} must be a whole number, got {d[k]!r}"
    assert _whole(doc["unmatched_runs"]) and _whole(doc["total_pence"]), (
        "unmatched_runs and total_pence must be whole numbers"
    )


@pytest.mark.parametrize("run_path,data_dir", RUNS)
def test_totals_add_up(run_path, data_dir):
    """Each driver's total is the sum of its six pence components, and the grand total is the
    sum of the drivers' totals."""
    doc = _load(run_path)
    for d in doc["drivers"]:
        assert d["total_pence"] == sum(d[k] for k in PENCE_PARTS), (
            f"{d['driver_id']}: total_pence {d['total_pence']} is not the sum of its components"
        )
    assert doc["total_pence"] == sum(d["total_pence"] for d in doc["drivers"]), (
        "total_pence is not the sum of the drivers' totals"
    )


@pytest.mark.parametrize("run_path,data_dir", RUNS)
def test_unmatched_runs(run_path, data_dir):
    """Rows for drivers who are not on the book are counted, whatever their status."""
    doc, exp = _load(run_path), expected(data_dir)
    assert doc["unmatched_runs"] == exp["unmatched_runs"], (
        f"unmatched_runs is {doc['unmatched_runs']}, expected {exp['unmatched_runs']}: every row "
        f"whose driver_id is not in drivers.csv counts once, whatever its status"
    )


@pytest.mark.parametrize("run_path,data_dir", RUNS)
def test_every_driver_matches(run_path, data_dir):
    """Every figure for every driver equals the pay run computed here from the same files."""
    doc, exp = _load(run_path), expected(data_dir)
    got = {d["driver_id"]: d for d in doc["drivers"]}
    wrong = []
    for e in exp["drivers"]:
        g = got.get(e["driver_id"])
        if g is None:
            wrong.append((e["driver_id"], "missing"))
            continue
        diff = {k: (g[k], e[k]) for k in DRIVER_KEYS[1:] if g[k] != e[k]}
        if diff:
            wrong.append((e["driver_id"], diff))
    assert not wrong, (
        f"{len(wrong)} driver(s) differ from the pay run computed from the same files, e.g. "
        f"{wrong[:3]}. Each figure follows a rule in SPEC.md; the field names say which"
    )

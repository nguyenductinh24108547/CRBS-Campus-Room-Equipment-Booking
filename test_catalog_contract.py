"""Structural contract checks for the 42-case design catalogue.

These checks validate completeness and traceability of test definitions only.
They DO NOT execute the business behavior of all 42 test cases.
Run: python -m pytest tests/test_catalog_contract.py -v
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "test_data" / "test_case_catalog.json"
RUNTIME_PATH = ROOT / "test_data" / "acceptance_test_data.json"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_catalog_contains_42_unique_case_definitions():
    catalog = load_json(CATALOG_PATH)
    cases = catalog["test_cases"]
    ids = [entry["test_case"]["test_case_id"] for entry in cases]
    assert len(cases) == 42
    assert len(ids) == len(set(ids))
    assert catalog["metadata"]["case_count"] == 42


def test_every_case_has_structured_test_data_definition():
    catalog = load_json(CATALOG_PATH)
    for entry in catalog["test_cases"]:
        tc_id = entry["test_case"]["test_case_id"]
        data = entry["test_data"]["input_parameters"]
        assert data["test_case_id"] == tc_id, tc_id
        assert data["test_data_id"], tc_id
        assert isinstance(data.get("setup"), dict), tc_id
        assert isinstance(data.get("input"), dict), tc_id
        assert isinstance(data.get("expected"), dict), tc_id
        assert isinstance(data.get("assertion"), (str, dict)) and data["assertion"], tc_id
        assert "definition_status" in data, tc_id
        assert isinstance(data.get("execution_ready"), bool), tc_id


def test_runtime_json_contains_exactly_the_declared_executable_cases():
    catalog = load_json(CATALOG_PATH)
    runtime = load_json(RUNTIME_PATH)
    catalog_ready = {
        entry["test_case"]["test_case_id"]
        for entry in catalog["test_cases"]
        if entry["test_data"]["input_parameters"]["execution_ready"]
    }
    runtime_ids = set(runtime["cases"])
    assert runtime_ids == catalog_ready
    assert len(runtime_ids) == 7


def test_runtime_cases_have_required_arrange_act_assert_fields():
    runtime = load_json(RUNTIME_PATH)
    for tc_id, case in runtime["cases"].items():
        assert isinstance(case.get("setup"), dict), tc_id
        assert isinstance(case.get("input"), dict), tc_id
        assert isinstance(case.get("expected"), dict), tc_id
        assert isinstance(case.get("purpose"), str) and case["purpose"].strip(), tc_id


def test_catalog_has_no_duplicate_test_data_ids():
    catalog = load_json(CATALOG_PATH)
    ids = [entry["test_data"]["input_parameters"]["test_data_id"] for entry in catalog["test_cases"]]
    assert len(ids) == len(set(ids))


def test_tc11_title_matches_the_actual_180_minute_test():
    catalog = load_json(CATALOG_PATH)
    item = next(entry for entry in catalog["test_cases"] if entry["test_case"]["test_case_id"] == "TC-11")
    data = item["test_data"]["input_parameters"]
    assert "more than two hours" in item["test_case"]["title"]
    assert data["input"]["now_minutes_before_start"] == 180
    assert "120 minutes" in data.get("review_note", "")


def test_generated_runtime_json_contains_excel_metadata_and_generator_source():
    runtime = load_json(RUNTIME_PATH)
    assert runtime["generator"] == "scripts/generate_test_data.py"
    assert runtime["source_sheets"] == ["test_cases", "test_data"]
    for tc_id, case in runtime["cases"].items():
        assert case["excel_metadata"]["test_data_id"] == case["data_id"], tc_id
        assert case["title"], tc_id
        assert case["setup"] is not None and case["input"] is not None, tc_id

"""Data-driven CRBS acceptance tests.

Each named test loads generated input from Excel-linked test_data/acceptance_test_data.json.
Regenerate it after editing the workbook/catalog with: python scripts/generate_test_data.py
Scope: educational Python/SQLite prototype in src/crbs.py. This is NOT evidence for a deployed group app.
Run from the package root:
    python -m pytest tests/test_campus_booking.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
import re

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "test_data" / "acceptance_test_data.json"
TEST_DATA = json.loads(DATA_PATH.read_text(encoding="utf-8"))
BASE_FIXTURE = TEST_DATA["base_fixture"]
CASES = TEST_DATA["cases"]

# Import the prototype from the package's src/ directory.
import sys
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from crbs import CRBS, CRBSError  # noqa: E402


@pytest.fixture
def ctx():
    """Arrange: create a clean in-memory DB and fixtures defined in JSON."""
    app = CRBS(student_weekly_quota=None)
    user_ids = {}
    resource_ids = {}

    for user in BASE_FIXTURE["users"]:
        user_ids[user["key"]] = app.add_user(
            user["display_name"], user["role"], user.get("email", "")
        )

    for resource in BASE_FIXTURE["resources"]:
        resource_ids[resource["key"]] = app.add_resource(
            resource["name"],
            resource["kind"],
            capacity=resource.get("capacity", 1),
            restricted=resource.get("restricted", False),
            allowed_roles=resource.get("allowed_roles"),
        )

    base_start = (
        datetime.now() + timedelta(days=BASE_FIXTURE["start_offset_days_from_now"])
    ).replace(
        hour=BASE_FIXTURE["start_hour"],
        minute=BASE_FIXTURE["start_minute"],
        second=0,
        microsecond=0,
    )

    context = {
        "app": app,
        "users": user_ids,
        "resources": resource_ids,
        "base_start": base_start,
    }
    try:
        yield context
    finally:
        app.close()


def load_case(tc_id: str) -> dict:
    """Read a test's purpose, setup, inputs and expected values from JSON."""
    if tc_id not in CASES:
        raise KeyError(f"No test-data definition found for {tc_id} in {DATA_PATH}")
    return CASES[tc_id]


def start_time(ctx: dict, params: dict) -> datetime:
    """Build a deterministic relative test time from the JSON offsets."""
    return ctx["base_start"] + timedelta(
        days=params.get("start_offset_days", 0),
        minutes=params.get("start_offset_minutes", 0),
    )


def submit_booking(ctx: dict, params: dict) -> tuple[int, datetime]:
    """Call the prototype's create_booking using the selected JSON fixture keys."""
    app = ctx["app"]
    start = start_time(ctx, params)
    end = start + timedelta(minutes=params["duration_minutes"])
    requester_id = ctx["users"][params["requester"]]
    resource_id = ctx["resources"][params["resource"]]
    bundled_ids = [
        ctx["resources"][key] for key in params.get("bundled_equipment", [])
    ]
    booking_id = app.create_booking(
        requester_id,
        resource_id,
        start.isoformat(timespec="minutes"),
        end.isoformat(timespec="minutes"),
        params["purpose"],
        attendees=params.get("attendees", 1),
        bundled_equipment_ids=bundled_ids,
    )
    return booking_id, start


def apply_setup(ctx: dict, setup: dict) -> list[int]:
    """Create any pre-existing bookings and maintenance incidents from JSON."""
    app = ctx["app"]
    booking_ids = []
    for incident in setup.get("maintenance_resources", []):
        app.log_maintenance(
            ctx["resources"][incident["resource"]],
            ctx["users"]["facility_staff"],
            incident["description"],
        )
    for params in setup.get("bookings_before_action", []):
        booking_id, _ = submit_booking(ctx, params)
        booking_ids.append(booking_id)
    return booking_ids


def find_booking(ctx: dict, booking_id: int):
    return next(
        booking for booking in ctx["app"].list_bookings()
        if booking["id"] == booking_id
    )


def test_TC01_available_room_booking_creates_pending(ctx):
    """TC-01: a valid room request should be created in Pending."""
    case = load_case("TC-01")
    apply_setup(ctx, case["setup"])
    booking_id, _ = submit_booking(ctx, case["input"])  # Act
    booking = find_booking(ctx, booking_id)
    assert booking["status"] == case["expected"]["status"]  # Assert


def test_TC02_overlapping_room_booking_is_rejected(ctx):
    """TC-02: an overlapping request must not create a second booking."""
    case = load_case("TC-02")
    apply_setup(ctx, case["setup"])  # Arrange: create the first booking
    with pytest.raises(CRBSError, match=re.escape(case["expected"]["error_contains"])):
        submit_booking(ctx, case["input"])  # Act: submit overlapping request
    assert len(ctx["app"].list_bookings()) == case["expected"]["existing_booking_count_after"]


def test_TC03_facility_staff_can_approve_pending_booking(ctx):
    """TC-03: authorized Facility Staff can approve a Pending booking."""
    case = load_case("TC-03")
    booking_ids = apply_setup(ctx, case["setup"])
    booking_id = booking_ids[-1]
    ctx["app"].decide_booking(
        booking_id,
        ctx["users"][case["input"]["decision_actor"]],
        case["input"]["decision"],
        case["input"]["reason"],
    )  # Act
    booking = find_booking(ctx, booking_id)
    assert booking["status"] == case["expected"]["status"]
    assert len(ctx["app"].notifications_for(ctx["users"]["student"])) == case["expected"]["notification_count"]


def test_TC05_maintenance_equipment_cannot_be_booked(ctx):
    """TC-05: equipment under maintenance blocks the whole bundle request."""
    case = load_case("TC-05")
    apply_setup(ctx, case["setup"])
    with pytest.raises(CRBSError, match=re.escape(case["expected"]["error_contains"])):
        submit_booking(ctx, case["input"])
    assert len(ctx["app"].list_bookings()) == case["expected"]["booking_count_after"]


def test_TC06_student_cannot_book_restricted_vip_room(ctx):
    """TC-06: a Student outside the allow-list cannot book the VIP room."""
    case = load_case("TC-06")
    apply_setup(ctx, case["setup"])
    with pytest.raises(CRBSError, match=re.escape(case["expected"]["error_contains"])):
        submit_booking(ctx, case["input"])
    assert len(ctx["app"].list_bookings()) == case["expected"]["booking_count_after"]


def test_TC11_owner_can_cancel_more_than_two_hours_before_start(ctx):
    """TC-11: the owner can cancel a valid booking three hours before its start."""
    case = load_case("TC-11")
    apply_setup(ctx, case["setup"])
    booking_id, start = submit_booking(ctx, case["input"])
    current_time = start - timedelta(minutes=case["input"]["now_minutes_before_start"])
    ctx["app"].cancel_booking(
        booking_id, ctx["users"][case["input"]["requester"]], now=current_time
    )  # Act
    booking = find_booking(ctx, booking_id)
    assert booking["status"] == case["expected"]["status"]


def test_TC26_room_and_bundled_equipment_are_one_request(ctx):
    """TC-26: the room and selected equipment are linked to one booking ID."""
    case = load_case("TC-26")
    apply_setup(ctx, case["setup"])
    booking_id, _ = submit_booking(ctx, case["input"])
    booking = find_booking(ctx, booking_id)
    rows = ctx["app"].db.execute(
        "SELECT resource_id, item_role FROM booking_items WHERE booking_id=?",
        (booking_id,),
    ).fetchall()
    assert booking["status"] == case["expected"]["status"]
    assert len(rows) == case["expected"]["booking_item_count"]
    assert {row["item_role"] for row in rows} == set(case["expected"]["item_roles"])

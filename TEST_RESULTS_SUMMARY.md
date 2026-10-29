# Test Results Summary

- Input-generation script: `python scripts/generate_test_data.py` — generated 7 executable runtime cases from Excel case/Test Data metadata joined with structured parameters in `test_data/test_case_catalog.json`.
- Catalog contract checks: 7 passed (structural/catalog consistency only).
- Acceptance tests: 7 passed against the educational Python/SQLite prototype.
- Prototype regression tests: 40 passed against the same prototype. PT-14 now deterministically schedules both bookings in the same calendar week; the prior failure was caused by a test setup that crossed a week boundary, not by the quota check itself.
- Combined pytest run (rerun 2026-10-16 after PT-14 test-data fix): 54 passed.

Scope limitation: this package does not prove the separate group/production application passes. Only seven catalog cases are marked execution-ready and run by the acceptance suite. The workbook has case descriptions and Test Data IDs but does not yet store every executable setup/input/expected parameter as dedicated Excel fields for all 42 cases; those structured definitions are joined from the JSON catalog. The other 35 cases remain design definitions, not executed behavior tests.

# QSD Phase-Bounded Transport - Testing Guide

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run smoke tests:
   ```bash
   python -m pytest tests/ -q --tb=short
   ```

3. Run full pipeline:
   ```bash
   make pipeline
   ```

4. (Optional) Run GitHub Actions locally with `act` if installed.

## Smoke Tests

The `tests/smoke_test.py` verifies:
- All core module imports
- Key helper functions (`robust_delta_e`, rolling stats)
- Pipeline initialization readiness

Full reproducibility checks are in `code/ligo_validation.py` and `code/validation_suite.py`.

**All tests should pass** after `make pipeline`.

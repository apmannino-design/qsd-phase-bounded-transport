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

Satellite optical-link prototype (simulation only):

```
python -m unittest tests.test_satellite_optical_link
python -m aurora_qsd.optical --all
```

See `docs/SATELLITE_OPTICAL_LINK.md`.

**All tests should pass** after `make pipeline`. Optical tests are independent of the GOES/LIGO pipeline.

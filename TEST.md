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

Conservative outer-loop + QSD sector phase law (tri-ΔE 3-stage lock-in):

```bash
python3 code/qsd_sector_closed_loop.py --self-test
```

Opto-acoustic frequency-matched residual loop:

```bash
python3 code/qsd_opto_acoustic.py --self-test
```

Spatial node-tracking match (two-source standing field):

```bash
python3 code/qsd_spatial_match.py --self-test
```

Cascaded plant (gap + phase + spatial) and disturbance battery:

```bash
python3 code/qsd_cascaded_plant.py --self-test
python3 code/run_qsd_disturbance_battery.py --self-test
```

Unified scorecard (headline: `rms_ratio = closed/open`):

```bash
python3 code/run_qsd_scorecard.py --self-test
```

**All tests should pass** after `make pipeline`.

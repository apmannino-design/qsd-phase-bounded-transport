# QSD Phase-Bounded Transport - Testing Guide

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run control-core self-tests (no `tests/` directory on this branch):
   ```bash
   python3 code/qsd_sector_closed_loop.py --self-test
   python3 code/qsd_opto_acoustic.py --self-test
   python3 code/qsd_spatial_match.py --self-test
   python3 code/qsd_cascaded_plant.py --self-test
   python3 code/run_qsd_disturbance_battery.py --self-test
   python3 code/run_qsd_scorecard.py --self-test
   ```

3. Run full pipeline:
   ```bash
   make pipeline
   ```

## QSD × Aalyria Spacetime

```bash
python3 qsd_spacetime/test_upgrades.py
python3 qsd_spacetime/test_integration.py
python3 qsd_spacetime/qsd_stack_v2.py test
python3 qsd_spacetime/test_qsd_stack_v2.py          # asserting unit tests
# python3 qsd_spacetime/bench_qsd_stack_v2.py       # long equal-budget benchmark (not CI)
scripts/verify_qsd_spacetime.sh
scripts/qsd_doctor.sh
```

**Merge order:** PR #14 then PR #15 onto `main`.

**All listed self-tests / spacetime suites should pass** after `make pipeline` / `make spacetime-verify`.

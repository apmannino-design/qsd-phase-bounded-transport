.PHONY: all pipeline report paper clean help spacetime spacetime-fetch spacetime-verify

all: pipeline report paper

spacetime-fetch:
	bash scripts/fetch_aalyria_spacetime.sh

spacetime:
	bash scripts/regen_qsd_spacetime_protos.sh
	python3 qsd_spacetime/test_upgrades.py
	python3 qsd_spacetime/test_integration.py
	python3 qsd_spacetime/qsd_stack_v2.py test
	python3 qsd_spacetime/test_qsd_stack_v2.py

spacetime-verify:
	bash scripts/verify_qsd_spacetime.sh
	python3 qsd_spacetime/test_upgrades.py
	python3 qsd_spacetime/qsd_stack_v2.py test
	python3 qsd_spacetime/test_qsd_stack_v2.py
	bash scripts/spacetime_staging_dryrun.sh
	bash scripts/qsd_terminal_pipeline.sh --sim --seconds 2
	bash scripts/qsd_doctor.sh

pipeline:
	python3 code/qsd_pipeline.py
	python3 code/figure_builder.py
	python3 code/validation_suite.py
	python3 code/domain_comparison.py
	python3 code/ligo_validation.py
	python3 code/surrogate_validation.py
	python3 code/spectral_null_validation.py
	python3 code/master_summary.py
	python3 code/qsd_sector_closed_loop.py --self-test
	python3 code/qsd_sector_closed_loop.py --out-dir results
	python3 code/qsd_opto_acoustic.py --self-test
	python3 code/qsd_opto_acoustic.py --out-dir results
	python3 code/qsd_spatial_match.py --self-test
	python3 code/qsd_spatial_match.py --out-dir results
	python3 code/qsd_cascaded_plant.py --self-test
	python3 code/qsd_cascaded_plant.py --out-dir results
	python3 code/run_qsd_disturbance_battery.py --self-test
	python3 code/run_qsd_disturbance_battery.py --out-dir results
	python3 code/run_qsd_scorecard.py --self-test
	python3 code/run_qsd_scorecard.py --out-dir results
	python3 qsd_spacetime/test_upgrades.py
	python3 qsd_spacetime/test_integration.py
	python3 qsd_spacetime/qsd_stack_v2.py test
	python3 qsd_spacetime/test_qsd_stack_v2.py

report:
	python3 code/build_report.py

paper:
	pandoc reports/qsd_report.md -o reports/qsd_report.pdf
	@echo "PDF report generated."

clean:
	rm -rf results/*
	rm -rf reports/*
	@echo "Cleaned generated outputs."

help:
	@echo "Available commands:"
	@echo "make all              - run full pipeline and build report + PDF"
	@echo "make pipeline         - run analysis only"
	@echo "make spacetime        - regen Aalyria protos + run qsd_spacetime tests"
	@echo "make spacetime-fetch  - re-clone aalyria/api + nmts + googleapis"
	@echo "make spacetime-verify - full verify (protos, bridge, Go agent dry-run)"
	@echo "make report           - generate markdown report only"
	@echo "make paper            - generate PDF report only"
	@echo "make clean            - remove generated outputs"

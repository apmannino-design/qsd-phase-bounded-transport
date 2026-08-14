.PHONY: all pipeline report paper optical clean help

all: pipeline report paper

pipeline:
	python3 code/qsd_pipeline.py
	python3 code/figure_builder.py
	python3 code/validation_suite.py
	python3 code/domain_comparison.py
	python3 code/ligo_validation.py
	python3 code/surrogate_validation.py
	python3 code/spectral_null_validation.py
	python3 code/master_summary.py

report:
	python3 code/build_report.py

paper:
	pandoc reports/qsd_report.md -o reports/qsd_report.pdf
	@echo "PDF report generated."

optical:
	python3 -m aurora_qsd.optical --all --seconds 4 --seed 0
	python3 -m unittest tests.test_satellite_optical_link

clean:
	rm -rf results/*
	rm -rf reports/*
	@echo "Cleaned generated outputs."

help:
	@echo "Available commands:"
	@echo "make all       - run full pipeline and build report + PDF"
	@echo "make pipeline  - run analysis only"
	@echo "make report    - generate markdown report only"
	@echo "make paper     - generate PDF report only"
	@echo "make optical   - run satellite FSO prototype + unit tests"
	@echo "make clean     - remove generated outputs"

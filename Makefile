all: pipeline report

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

clean:
	rm -rf results/*
	rm -rf reports/*
	echo "Cleaned generated outputs."

help:
	@echo "Available commands:"
	@echo "make all       - run full pipeline and build report"
	@echo "make pipeline  - run analysis only"
	@echo "make report    - generate report only"
	@echo "make clean     - remove generated outputs"

#!/bin/bash

echo "Running GOES pipeline..."
python3 code/qsd_pipeline.py

echo "Building GOES figures..."
python3 code/figure_builder.py

echo "Running Kp validation..."
python3 code/validation_suite.py

echo "Generating cross-domain comparison..."
python3 code/domain_comparison.py

echo "Pipeline complete."
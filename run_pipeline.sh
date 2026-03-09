#!/bin/bash

echo "Running GOES QSD pipeline..."
python3 code/qsd_pipeline.py

echo "Building GOES figures..."
python3 code/figure_builder.py

echo "Running Kp validation suite..."
python3 code/validation_suite.py

echo "Done."
echo "Check results/ and results/figures_generated/"
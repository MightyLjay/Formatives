"""The model — only now, and distributional.

We don't need E[2H points]. We need P(2H > line). Predict a distribution, not a mean; calibration
is what we bet on, not accuracy. Benchmark against the closing line's MAE and log-loss. Nothing
else is a benchmark.
"""

"""Halftime state from play-by-play — with leakage made impossible, not merely unlikely.

Any feature that touches a PBP event after the halftime buzzer silently biases the model. The
leakage guard in this package raises on that, and tests/test_leakage.py fails the build on it.
"""

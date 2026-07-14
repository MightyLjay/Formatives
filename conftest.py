"""Ensure the repo root is importable so `import eval`, `import market`, etc. resolve to our
packages regardless of where pytest is invoked from."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

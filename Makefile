.PHONY: help install test eval market collect intel kill clean

help:
	@echo "h2-totals-lab"
	@echo "  make install   install the tested-core deps (numpy/pandas/scipy/pytest)"
	@echo "  make test      run the full test suite (incl. the leakage build-gate)"
	@echo "  make eval      run the falsification harness on synthetic data"
	@echo "  make market    run the market layer demo (fixture provider, offline)"
	@echo "  make collect   run one collector cycle (needs a live feed / config)"
	@echo "  make intel     run the intel-extract demo (needs ANTHROPIC_API_KEY)"
	@echo "  make kill      run the executable kill-criteria checks (exits non-zero to KILL)"

install:
	python -m pip install -r requirements.txt

test:
	python -m pytest

eval:
	python -m eval.demo

market:
	python -m market.poll --demo

collect:
	python -m collector.run

intel:
	python -m intel.extract --demo

kill:
	python -m eval.kill

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache

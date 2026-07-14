.PHONY: help install install-live install-dashboard test eval market collect intel probe monitor dashboard kill clean

help:
	@echo "h2-totals-lab"
	@echo "  make install   install the tested-core deps (numpy/pandas/scipy/pytest)"
	@echo "  make test      run the full test suite (incl. the leakage build-gate)"
	@echo "  make eval      run the falsification harness on synthetic data"
	@echo "  make market    run the market layer demo (fixture provider, offline)"
	@echo "  make collect   run one collector cycle (offline demo)"
	@echo "  make intel     run the intel-extract demo (needs ANTHROPIC_API_KEY)"
	@echo "  make probe     probe a live odds feed for 2H totals (needs ODDS_API_KEY + network)"
	@echo "  make monitor   continuously monitor live 2H odds (needs ODDS_API_KEY + network)"
	@echo "  make dashboard launch the local Streamlit dashboard in your browser"
	@echo "  make kill      run the executable kill-criteria checks (exits non-zero to KILL)"

install:
	python -m pip install -r requirements.txt

install-live:
	python -m pip install -r requirements.txt -r requirements-extra.txt

install-dashboard:
	python -m pip install -r requirements.txt -r requirements-dashboard.txt

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

probe:
	python -m market.probe

monitor:
	python -m collector.monitor --dry-run

dashboard:
	streamlit run dashboard/app.py

kill:
	python -m eval.kill

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache

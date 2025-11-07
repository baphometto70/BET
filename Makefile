# ========= Makefile – Scommesse (versione stabile) =========
SHELL := /bin/bash

PY      ?= python
DATE    ?= $(shell date -u +"%Y-%m-%d")
COMPS   ?= SA,PL,PD,BL1
NREC    ?= 5
DELAY   ?= 0.6
PORT    ?= 5000
FROM    ?= 2023-07-01
TO      ?= $(shell date -u +"%Y-%m-%d")
REQ     ?= requirements.txt
VENV    ?= .venv

PRED    := predictions.csv
REPORT  := report.html

.PHONY: help setup ui daily daily-smart fixtures odds features predict train dummy history open-report clean check-config check-csv

help:
	@echo "Comandi:"
	@echo "  make setup"
	@echo "  make ui [PORT=5000]"
	@echo "  make daily DATE=... COMPS=..."
	@echo "  make daily-smart DATE=... COMPS=..."
	@echo "  make fixtures DATE=... COMPS=..."
	@echo "  make odds DATE=... COMPS=..."
	@echo "  make features DATE=... COMPS=..."
	@echo "  make predict"
	@echo "  make train | make dummy"
	@echo "  make history FROM=... TO=... COMPS=..."
	@echo "  make open-report | make clean"
	@echo "  make check-config | make check-csv DATE=..."

setup:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@source $(VENV)/bin/activate && pip install --upgrade pip && { test -f $(REQ) && pip install -r $(REQ) || true; }
	@echo "✅ Setup completato. Attiva con: source $(VENV)/bin/activate"

ui:
	@BET_DASH_PORT=$(PORT) $(PY) app.py

daily: fixtures odds features predict
	@echo "✅ Pipeline giornaliera completata: $(DATE) [$(COMPS)]"

fixtures:
	@$(PY) run_day.py --date "$(DATE)" --comps "$(COMPS)" --delay $(DELAY)

odds:
	@$(PY) odds_fetcher.py --date "$(DATE)" --comps "$(COMPS)" --delay 0.3

features:
	@$(PY) features_populator.py --date "$(DATE)" --comps "$(COMPS)" --n_recent $(NREC) --delay $(DELAY) --cache 1

predict:
	@$(PY) model_pipeline.py --predict
	@echo "➡️  Output: $(PRED), $(REPORT)"

train:
	@$(PY) model_pipeline.py --train

dummy:
	@$(PY) model_pipeline.py --train-dummy

history:
	@$(PY) historical_builder.py --from $(FROM) --to $(TO) --comps "$(COMPS)" --n_recent $(NREC) --delay $(DELAY)
	@echo "➡️  Output: data/historical_dataset.csv"

open-report:
	@if [ -f "$(REPORT)" ]; then open "$(REPORT)"; else echo "Report non trovato: $(REPORT)"; fi

clean:
	@rm -rf __pycache__ */__pycache__ .pytest_cache .mypy_cache
	@rm -f *.png
	@echo "🧹 Pulizia minima effettuata."

# --------- CHECKS (senza heredoc) ----------
check-config:
	@$(PY) tools/checks.py config

check-csv:
	@echo "🔎 Verifica config..."
	@$(PY) tools/checks.py config
	@echo "🔎 Verifica fixtures $(DATE)..."
	@$(PY) tools/checks.py fixtures --date "$(DATE)" || $(MAKE) fixtures
	@echo "🔎 Verifica odds $(DATE)..."
	@$(PY) tools/checks.py odds --date "$(DATE)" || $(MAKE) odds
	@echo "🔎 Verifica features $(DATE)..."
	@$(PY) tools/checks.py features --date "$(DATE)" || $(MAKE) features
	@echo "✅ CSV ok per $(DATE)."

# --------- PIPELINE SMART ----------
daily-smart: check-csv predict
	@echo "✅ Pipeline smart completata: $(DATE) [$(COMPS)]"

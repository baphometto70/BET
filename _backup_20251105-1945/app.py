#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shlex
import subprocess
import threading
import time
from datetime import date
from pathlib import Path

from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

ROOT = Path(__file__).resolve().parent
APP = Flask(__name__)
APP.secret_key = "dev-local-only"
APP.config["TEMPLATES_AUTO_RELOAD"] = True

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
CURRENT_LOG = LOGS_DIR / "current.log"

# stato semplice del job
_job_lock = threading.Lock()
_job_running = False
_job_name = None  # "daily" | "history" | "train" | "predict"


# ---- Niente cache sul browser (evita pagine “ferme”) ----
@APP.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ---- Ping di diagnostica ----
@APP.get("/ping")
def ping():
    return make_response("pong", 200)


# Codici competizioni mostrati in UI
COMP_CHOICES = [
    ("SA", "Serie A"),
    ("PL", "Premier League"),
    ("PD", "Primera Division"),
    ("BL1", "Bundesliga"),
    ("FL1", "Ligue 1"),
    ("DED", "Eredivisie"),
    ("PPL", "Primeira Liga"),
    ("ELC", "Championship (ENG)"),
    ("CL", "UEFA Champions League"),
    ("EL", "UEFA Europa League"),
]


def _append_log(text: str):
    with open(CURRENT_LOG, "a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def run_cmd(cmd: str):
    """Esegue un comando nella root del progetto e logga stdout/stderr su CURRENT_LOG."""
    _append_log(f"$ {cmd}\n")
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        if proc.stdout:
            _append_log(proc.stdout)
        if proc.stderr:
            _append_log("--- STDERR ---")
            _append_log(proc.stderr)
    except Exception as e:
        _append_log(f"[ERRORE] {e}")


def job_wrapper(target_name: str, func, *args, **kwargs):
    global _job_running, _job_name
    with _job_lock:
        if _job_running:
            _append_log(
                f"[INFO] Job già in esecuzione: '{_job_name}'. Ignoro nuova richiesta."
            )
            return
        _job_running = True
        _job_name = target_name
    try:
        # reset log all’avvio del job
        CURRENT_LOG.write_text(
            f"[START] {target_name} — {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
            encoding="utf-8",
        )
        func(*args, **kwargs)
        _append_log(f"[END] {target_name} — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    finally:
        with _job_lock:
            _job_running = False
            _job_name = None


def run_daily_pipeline(d: str, comps: str, delay: str, do_predict: bool):
    run_cmd(f'python run_day.py --date {d} --comps "{comps}" --delay {delay}')
    run_cmd(f'python odds_fetcher.py --date {d} --comps "{comps}" --delay 0.3')
    run_cmd(
        f'python features_populator.py --date {d} --comps "{comps}" --n_recent 5 --delay {delay} --cache 1'
    )
    if do_predict:
        run_cmd("python model_pipeline.py --predict")


def run_history_builder(dfrom: str, dto: str, comps: str, nrec: str, delay: str):
    run_cmd(
        f'python historical_builder.py --from {dfrom} --to {dto} --comps "{comps}" --n_recent {nrec} --delay {delay}'
    )


def run_training(mode: str):
    if mode == "dummy":
        run_cmd("python model_pipeline.py --train-dummy")
    else:
        run_cmd("python model_pipeline.py --train")


def run_predict_only():
    run_cmd("python model_pipeline.py --predict")


def _read_last_log_tail(max_chars: int = 12000) -> str:
    if not CURRENT_LOG.exists():
        return ""
    data = CURRENT_LOG.read_text(encoding="utf-8", errors="ignore")
    # tail “povero”: mostra solo le ultime N chars per non pesare in pagina
    return data[-max_chars:]


def current_state(today_override: str | None = None) -> dict:
    return {
        "today": today_override or date.today().isoformat(),
        "has_hist": (ROOT / "data" / "historical_dataset.csv").exists(),
        "has_model": (ROOT / "models" / "bet_ou25.joblib").exists(),
        "has_report": (ROOT / "report.html").exists(),
        "has_preds": (ROOT / "predictions.csv").exists(),
        "job_running": _job_running,
        "job_name": _job_name or "",
    }


# ====== HOME ======
@APP.get("/")
def index():
    return render_template(
        "index.html",
        comp_choices=COMP_CHOICES,
        state=current_state(),
        last_log=_read_last_log_tail(),
        active_tab="daily",
    )


# ====== DAILY ======
@APP.post("/daily", endpoint="daily")
def daily():
    d = request.form.get("date") or date.today().isoformat()
    comps_list = request.form.getlist("comps") or ["SA", "PL", "PD", "BL1"]
    comps = ",".join(comps_list)
    delay = request.form.get("delay", "0.6")
    do_predict = request.form.get("do_predict") == "on"

    if _job_running:
        flash("Un job è già in esecuzione. Attendi che termini.")
    else:
        t = threading.Thread(
            target=job_wrapper,
            args=("daily", run_daily_pipeline, d, comps, delay, do_predict),
            daemon=True,
        )
        t.start()
        flash(f"Pipeline del giorno avviata per {d} [{comps}]. Controlla i log.")

    return render_template(
        "index.html",
        comp_choices=COMP_CHOICES,
        state=current_state(today_override=d),
        last_log=_read_last_log_tail(),
        active_tab="daily",
    )


# ====== HISTORY ======
@APP.post("/history", endpoint="history")
def history():
    dfrom = request.form.get("from") or "2023-07-01"
    dto = request.form.get("to") or date.today().isoformat()
    comps_list = request.form.getlist("comps_hist") or ["SA", "PL", "PD", "BL1"]
    comps = ",".join(comps_list)
    nrec = request.form.get("n_recent_hist", "5")
    delay = request.form.get("delay_hist", "0.6")

    if _job_running:
        flash("Un job è già in esecuzione. Attendi che termini.")
    else:
        t = threading.Thread(
            target=job_wrapper,
            args=("history", run_history_builder, dfrom, dto, comps, nrec, delay),
            daemon=True,
        )
        t.start()
        flash(f"Storico avviato: {dfrom} → {dto} [{comps}]. Controlla i log.")

    return render_template(
        "index.html",
        comp_choices=COMP_CHOICES,
        state=current_state(),
        last_log=_read_last_log_tail(),
        active_tab="history",
    )


# ====== TRAIN ======
@APP.post("/train", endpoint="train")
def train():
    mode = request.form.get("train_mode", "real")  # real | dummy
    if _job_running:
        flash("Un job è già in esecuzione. Attendi che termini.")
    else:
        t = threading.Thread(
            target=job_wrapper, args=("train", run_training, mode), daemon=True
        )
        t.start()
        flash(f"Training '{mode}' avviato. Controlla i log.")

    return render_template(
        "index.html",
        comp_choices=COMP_CHOICES,
        state=current_state(),
        last_log=_read_last_log_tail(),
        active_tab="history",
    )


# ====== PREDICT ======
@APP.post("/predict", endpoint="predict")
def predict():
    if _job_running:
        flash("Un job è già in esecuzione. Attendi che termini.")
    else:
        t = threading.Thread(
            target=job_wrapper, args=("predict", run_predict_only), daemon=True
        )
        t.start()
        flash("Predizione avviata. Controlla i log.")

    return render_template(
        "index.html",
        comp_choices=COMP_CHOICES,
        state=current_state(),
        last_log=_read_last_log_tail(),
        active_tab="predict",
    )


# ====== DOWNLOAD ======
@APP.get("/download/<path:fname>")
def download(fname):
    p = (ROOT / fname).resolve()
    if not p.exists():
        flash("File non trovato.")
        return redirect(url_for("index"))
    return send_from_directory(
        directory=str(p.parent), path=p.name, as_attachment=False
    )


def main():
    APP.run(
        host="127.0.0.1",
        port=int(os.getenv("BET_DASH_PORT", "5000")),
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
import sys

# --- Controllo Dipendenze Essenziali ---
try:
    # tomllib è standard in Python 3.11+, tomli è per versioni precedenti.
    # Questo blocco assicura che uno dei due sia disponibile.
    import tomllib
except ImportError:
    try:
        import tomli
    except ImportError:
        print("\n[FATAL] Dipendenza mancante: 'tomli'. L'applicazione non può avviarsi.", file=sys.stderr)
        print("        Esegui questo comando nel tuo ambiente virtuale e riavvia:", file=sys.stderr)
        print("        pip install tomli\n", file=sys.stderr)
        sys.exit(1)
# --- Fine Controllo ---

import shlex
import subprocess
import threading
import time
from datetime import date
from functools import partial
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _HAS_APS = True
except Exception:
    _HAS_APS = False
from pathlib import Path
from typing import Optional
import atexit
import socket
import sys # Import sys

try:
    from database import SessionLocal
    from models import Feature, Fixture, Odds
    from sqlalchemy import func
except ImportError:
    # Gestisce il caso in cui il DB non sia configurato, per evitare crash all'avvio.
    SessionLocal = None
    Fixture = Odds = Feature = None
    func = None
    print("[WARN] Modelli DB o SQLAlchemy non trovati. Le funzionalità legate ai dati saranno disabilitate.", file=sys.stderr)

from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    jsonify,
    url_for,
)

ROOT = Path(__file__).resolve().parent

# Preferisci il DB SQLite locale e una cache Matplotlib scrivibile per test via web app
os.environ.setdefault("USE_SQLITE", "1")
MPLCONFIG_DIR = Path.home() / ".cache" / "bet_mpl"
MPLCONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIG_DIR))

AUTO_FIXTURES_ENABLED = os.getenv("AUTO_FIXTURES_ENABLED", "1") == "1"
AUTO_FIXTURES_COMPS = os.getenv("AUTO_FIXTURES_COMPS", "SA,PL,PD,BL1,FL1,DED,PPL")
AUTO_FIXTURES_MIN_DAYS = int(os.getenv("AUTO_FIXTURES_MIN_DAYS", "7"))
AUTO_FIXTURES_TARGET_DAYS = int(os.getenv("AUTO_FIXTURES_TARGET_DAYS", "30"))

APP = Flask(__name__)
APP.secret_key = "dev-local-only"
APP.config["TEMPLATES_AUTO_RELOAD"] = True

LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# --- CONFIGURAZIONE LOGGING ---
# Sostituisco la gestione manuale dei file con il modulo standard `logging`.
# Questo fornisce timestamp, livelli di log (INFO, ERROR) e un formato strutturato.
LOG_FILE = LOGS_DIR / "service.log"

# Configura il logger principale
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler() # Mostra i log anche a console
    ]
)
logger = logging.getLogger(__name__)

# Definisci qui i percorsi dei file di output per poterli gestire centralmente
PRED_PATH = ROOT / "predictions.csv"
REPORT_HTML = ROOT / "report.html"

# stato semplice del job
_job_lock = threading.Lock()
_job_running = False
_job_name = None  # "daily" | "history" | "train" | "predict"
_job_last_message = "" # Messaggio finale del job (successo/errore)
_job_stop_requested = False # Flag per interrompere un job
_child_processes = [] # Lista per tenere traccia dei processi figli

def _log_fixture_coverage(min_days_left: int = 7, target_days: int = 30):
    """
    Avvisa se il DB ha fixture troppo vicine nel tempo (serve aggiornare).
    Logga la massima data presente e quanti giorni di copertura restano.
    """
    days_left = None
    if not SessionLocal or not Fixture or not func:
        return days_left
    db = SessionLocal()
    try:
        max_date = db.query(func.max(Fixture.date)).scalar()
        if not max_date:
            logger.warning("DB fixture vuoto. Esegui `python fixtures_fetcher.py --date YYYY-MM-DD --days 30 --comps \"SA,PL,PD,BL1,FL1,DED,PPL\"`.")
            return days_left
        days_left = (max_date - date.today()).days
        if days_left < min_days_left:
            logger.warning(
                f"Copertura fixture solo fino al {max_date} (tra {days_left} giorni). "
                f"Esegui `python fixtures_fetcher.py --date {date.today().isoformat()} --days {target_days} --comps \"SA,PL,PD,BL1,FL1,DED,PPL\"`."
            )
        else:
            logger.info(f"Fixture presenti fino al {max_date} (copertura ~{days_left} giorni).")
    except Exception as exc:
        logger.debug(f"Errore nel controllo copertura fixture: {exc}", exc_info=True)
    finally:
        db.close()
    return days_left


def _cleanup_child_processes():
    """Funzione di pulizia registrata con atexit per terminare i processi figli."""
    for p in _child_processes:
        if p.poll() is None:  # Se il processo è ancora in esecuzione
            print(f"\n[EXIT] Termino il processo figlio in background (PID: {p.pid})...", file=sys.stderr)
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()

atexit.register(_cleanup_child_processes)


def _auto_fetch_fixtures_if_needed():
    """Se la copertura è bassa e auto fetch è abilitato, lancia fixtures_fetcher."""
    if not AUTO_FIXTURES_ENABLED:
        logger.info("Auto fetch fixtures disabilitato (AUTO_FIXTURES_ENABLED=0).")
        return
    days_left = _log_fixture_coverage(AUTO_FIXTURES_MIN_DAYS, AUTO_FIXTURES_TARGET_DAYS)
    if days_left is None:
        return
    if days_left >= AUTO_FIXTURES_MIN_DAYS:
        return
    cmd = (
        f"{sys.executable} fixtures_fetcher.py "
        f"--date {date.today().isoformat()} "
        f"--days {AUTO_FIXTURES_TARGET_DAYS} "
        f'--comps "{AUTO_FIXTURES_COMPS}"'
    )
    logger.info(f"[AUTO] Copertura bassa ({days_left} giorni). Avvio fetch fixtures: {cmd}")
    ok = run_cmd(cmd, timeout=1800)
    if ok:
        logger.info("[AUTO] Fetch fixtures completato.")
    else:
        logger.error("[AUTO] Fetch fixtures fallito.")

# Controllo immediato copertura fixture all'avvio (dopo la definizione delle funzioni)


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


def run_cmd(cmd: str, timeout: int = 3600):
    """Esegue un comando, logga in tempo reale ed è interrompibile."""
    global _job_stop_requested, _child_processes

    cmd_parts = shlex.split(cmd)
    if cmd_parts and cmd_parts[0] == "python":
        cmd_parts[0] = sys.executable

    # Logga il comando in modo sicuro per la shell
    log_cmd = " ".join(shlex.quote(c) for c in cmd_parts)
    logger.info(f"Esecuzione comando: $ {log_cmd}")
    proc = None
    try:
        # Usa Popen per avere controllo non bloccante sul processo
        proc = subprocess.Popen(
            cmd_parts,  # Passa la lista di argomenti direttamente
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Unisci stderr in stdout
            text=True,
            encoding='utf-8',
            errors='replace',
            env=os.environ.copy(),
        )
        _child_processes.append(proc)

        # Un solo thread per leggere l'output combinato
        def log_pipe(pipe):
            buffer = []
            last_flush_time = time.time()
            try:
                for line in iter(pipe.readline, ''):
                    buffer.append(line.strip())
                    # Scrivi il buffer ogni 0.5 secondi o se raggiunge 20 righe
                    # per ridurre il numero di operazioni di scrittura su file.
                    now = time.time()
                    if buffer and (now - last_flush_time > 0.5 or len(buffer) >= 20):
                        logger.info("\n".join(buffer))
                        buffer.clear()
                        last_flush_time = now
            finally:
                # Assicurati di scrivere le righe rimanenti nel buffer prima di uscire
                if buffer:
                    logger.info("\n".join(buffer))
                pipe.close()

        stdout_thread = threading.Thread(target=log_pipe, args=(proc.stdout,))
        stdout_thread.start()

        start_time = time.time()
        while proc.poll() is None:  # Finché il processo è in esecuzione
            with _job_lock:
                if _job_stop_requested:
                    logger.warning("Richiesta di interruzione ricevuta. Termino il processo...")
                    proc.terminate()  # Invia SIGTERM (più "gentile")
                    try:
                        proc.wait(timeout=5)  # Attendi 5s che termini
                    except subprocess.TimeoutExpired:
                        logger.warning("Il processo non ha risposto, forzo la chiusura (kill).")
                        proc.kill()  # Invia SIGKILL (forzato)
                    stdout_thread.join(timeout=5)
                    return False  # Il job è stato interrotto

            if time.time() - start_time > timeout:
                logger.error(f"Timeout dopo {timeout}s per il comando: {log_cmd}")
                proc.terminate()
                proc.kill()
                stdout_thread.join()
                return False

            time.sleep(0.2)  # Polling per non usare 100% CPU

        # Attendi che il thread di logging finisca
        stdout_thread.join(timeout=10) # Aggiungi timeout per sicurezza

        if proc.returncode != 0:
            logger.error(f"Comando fallito con exit code {proc.returncode}: {log_cmd}")
        return proc.returncode == 0
    except Exception as e:
        logger.error(f"Eccezione durante l'esecuzione del comando: {e}", exc_info=True)
        return False
    finally:
        if proc and proc in _child_processes:
            _child_processes.remove(proc)

# Controllo immediato copertura fixture all'avvio (dopo la definizione delle funzioni principali)
_log_fixture_coverage()
_auto_fetch_fixtures_if_needed()


def job_wrapper(target_name: str, func, *args, **kwargs):
    """Wraps a job function to handle state and logging."""
    global _job_running, _job_name, _job_last_message, _job_stop_requested    
    success = False
    try:
        logger.info(f"--- Inizio Job: {target_name} ---")
        success = func(*args, **kwargs)
        logger.info(f"--- Fine Job: {target_name} (Successo: {success}) ---")
    finally:
        with _job_lock:
            job_was_stopped = _job_stop_requested
            if job_was_stopped:
                _job_last_message = f"Job '{target_name}' interrotto dall'utente."
            elif success:
                _job_last_message = f"Job '{target_name}' completato con successo."
            else:
                _job_last_message = f"Job '{target_name}' fallito o completato con errori."
            _job_running = False
            _job_name = None
            _job_stop_requested = False # Resetta per sicurezza


def run_daily_pipeline(d: str, comps: str, delay: str, do_predict: bool):
    """Esegue la pipeline giornaliera completa."""
    # AZIONE CRITICA: Pulisci i file di output vecchi all'inizio di ogni esecuzione.
    # Questo previene la visualizzazione di dati stantii se la pipeline fallisce.
    if REPORT_HTML.exists():
        try:
            REPORT_HTML.unlink()
            logger.info("Vecchio report.html rimosso.")
        except OSError as e:
            logger.warning(f"Impossibile rimuovere vecchio report.html: {e}")
    if PRED_PATH.exists():
        try:
            PRED_PATH.unlink()
            logger.info("Vecchio predictions.csv rimosso.")
        except OSError as e:
            logger.warning(f"Impossibile rimuovere vecchio predictions.csv: {e}")
    
    # Step 1: Fetch fixtures
    logger.info(f"[PIPELINE 1/4] Recupero partite per {d}...")
    if not run_cmd(f'python fixtures_fetcher.py --date {d} --comps {comps}'):
        logger.error("Fetch fixtures fallito. Pipeline interrotta.")
        return False
    
    # Step 2: Fetch odds
    logger.info(f"[PIPELINE 2/4] Recupero quote per {d}...")
    if not run_cmd(f'python odds_fetcher.py --date {d} --comps {comps} --delay 0.3'):
        logger.warning("Fetch odds fallito (continuo comunque).")
    
    # Step 3: Populate features
    logger.info(f"[PIPELINE 3/4] Popolamento features per {d}...")
    if not run_cmd(
        f'python features_populator.py --date {d} --comps {comps} --n_recent 5 --delay {delay} --cache 1'
    ):
        logger.error("Popolamento features fallito. Pipeline interrotta.")
        return False
    
    # Step 4: Predictions
    if do_predict:
        logger.info(f"[PIPELINE 4/4] Generazione previsioni...")
        if not run_cmd(
            f'python model_pipeline.py --predict --date {d} --comps {comps}'
        ):
            logger.error("Generazione previsioni fallita.")
            return False
    
    logger.info("Pipeline giornaliera completata con successo.")
    return True


def run_history_builder(dfrom: str, dto: str, comps: str, nrec: str, delay: str):
    return run_cmd(
        f'python historical_builder.py --from {dfrom} --to {dto} --comps {comps} --n_recent {nrec} --delay {delay}'
    )


def run_training(mode: str):
    if mode == "dummy":
        return run_cmd("python model_pipeline.py --train-dummy")
    else:
        return run_cmd("python model_pipeline.py --train")


def run_predict_only():
    return run_cmd("python model_pipeline.py --predict")


def run_results_fetcher():
    """Esegue lo script per scaricare i risultati delle partite."""
    return run_cmd("python results_fetcher.py")


def run_map_builder():
    """Esegue lo script per costruire i mapping dei team."""
    return run_cmd("python map_builder.py")


def run_odds_bulk_fetch(days: str):
    """Esegue lo scaricamento massivo delle quote future per un numero di giorni specificato."""
    return run_cmd(f"python odds_fetcher.py --bulk-fetch --verbose --bulk-days {days}")


def get_odds_coverage_info() -> dict:
    """
    Controlla fino a che data sono presenti le quote nel DB
    e restituisce la data e un avviso se la copertura è bassa.
    """
    if not SessionLocal: # Controlla se il DB è disponibile
        return { "warning": True, "message": "Database non configurato." }

    db = SessionLocal()
    try:
        # Trova la data massima delle partite FUTURE per cui abbiamo le quote
        max_date_result = (
            db.query(func.max(Fixture.date))
            .join(Odds, Fixture.match_id == Odds.match_id)
            .filter(Fixture.date >= date.today()) # Considera solo le quote future
            .scalar()
        )

        if not max_date_result:
            # Se non ci sono quote future, controlla se esistono almeno le partite
            # per dare un messaggio di diagnostica più utile.
            future_fixtures_count = db.query(Fixture).filter(Fixture.date >= date.today()).count()
            if future_fixtures_count > 0:
                message = f"Trovate {future_fixtures_count} partite future, ma nessuna con quote. Lanciare il Bulk Fetch o controllare lo script 'odds_fetcher'."
            else:
                message = "Nessuna quota per partite future. Lancia il Bulk Fetch."

            return {
                "coverage_date": None,
                "coverage_days": 0,
                "warning": True,
                "message": message,
            }

        coverage_date = max_date_result
        today = date.today()
        days_left = (coverage_date - today).days

        # Avviso se la copertura è inferiore a 7 giorni
        warning = days_left < 7
        msg = f"Quote coperte fino al {coverage_date.strftime('%d/%m/%Y')}."
        if warning:
            msg += f" Mancano {days_left} giorni. Consigliato eseguire il Bulk Fetch."
        
        return { "coverage_date": coverage_date.isoformat(), "coverage_days": days_left, "warning": warning, "message": msg }
    except Exception as e:
        logger.error(f"Errore nel calcolo della copertura quote: {e}", exc_info=True)
        return { "warning": True, "message": "Errore nel calcolo della copertura quote." }
    finally:
        if db:
            db.close()
def _read_last_log_tail(max_chars: int = 12000) -> str:
    """Legge la coda del file di log per visualizzarla nella UI."""
    # NOTA: Con il nuovo sistema di logging, questo legge il file `service.log`.
    # L'output dei job viene catturato in tempo reale e loggato, quindi
    # questo file conterrà sia i log dell'app che l'output dei comandi.
    if not LOG_FILE.exists():
        return ""
    with open(LOG_FILE, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(f.tell() - max_chars, 0), os.SEEK_SET)
        return f.read().decode('utf-8', errors='ignore')


def get_job_status() -> dict:
    with _job_lock:
        return {
            "job_running": _job_running,
            "job_name": _job_name,
            "last_message": _job_last_message,
        }

def current_state(today_override: Optional[str] = None) -> dict:
    state = {
        "today": today_override or date.today().isoformat(),
        "has_hist": (ROOT / "data" / "historical_dataset.csv").exists(),
        "has_model": (ROOT / "models" / "bet_ou25.joblib").exists(), # Controlla un modello a caso
        "has_report": REPORT_HTML.exists(),
        "has_preds": PRED_PATH.exists(),
    }
    job_status = get_job_status()
    state["job_running"] = job_status["job_running"]
    state["job_name"] = job_status["job_name"] or ""
    state["last_message"] = job_status["last_message"]
    state["odds_coverage"] = get_odds_coverage_info()
    return state

def _start_job_and_render(
    job_name: str,
    target_func,
    args_tuple: tuple,
):
    global _job_running, _job_name, _job_last_message, _job_stop_requested
    with _job_lock:
        if _job_running:
            return jsonify({"status": "job_already_running", "job_name": _job_name, "message": f"Un job ('{_job_name}') è già in esecuzione. Attendi che termini."})

        # Imposta lo stato PRIMA di avviare il thread per evitare race condition
        _job_running = True
        _job_name = job_name
        _job_last_message = ""
        _job_stop_requested = False

        thread_args = (job_name, target_func) + args_tuple
        t = threading.Thread(target=job_wrapper, args=thread_args, daemon=True)
        t.start()
        
    return jsonify({"status": "job_started", "job_name": job_name})


def _schedule_start_job(job_name: str, target_func, args_tuple: tuple):
    """Start a job from scheduler (no Flask request). Returns True if started."""
    global _job_running, _job_name, _job_last_message, _job_stop_requested
    with _job_lock:
        if _job_running:
            logger.warning(f"[SCHED] Job '{job_name}' non avviato: un altro job ('{_job_name}') è in esecuzione.")
            return False

        # Imposta stato e avvia thread di esecuzione tramite job_wrapper
        _job_running = True
        _job_name = job_name
        _job_last_message = ""
        _job_stop_requested = False

        thread_args = (job_name, target_func) + args_tuple
        t = threading.Thread(target=job_wrapper, args=thread_args, daemon=True)
        t.start()

    logger.info(f"[SCHED] Job '{job_name}' avviato dallo scheduler.")
    return True


# ====== HOME ======
@APP.get("/")
def index():
    """Render the main dashboard page."""
    state = current_state()
    # Aggiungi un messaggio flash se la copertura delle quote è bassa o assente
    odds_coverage_info = state.get("odds_coverage", {})
    if odds_coverage_info.get("warning"):
        flash(odds_coverage_info.get("message", "Controllo copertura quote non riuscito."), "warning")

    return render_template(
        "index.html",
        comp_choices=COMP_CHOICES,
        state=state,
        last_log=_read_last_log_tail(),
        active_tab="daily",  # Set a default to keep details panels closed
    )


# ====== DAILY ======
@APP.post("/daily", endpoint="daily")
def daily():
    d = request.form.get("date") or date.today().isoformat()
    comps_list = request.form.getlist("comps") or ["SA", "PL", "PD", "BL1"]
    comps = ",".join(comps_list)
    delay = request.form.get("delay", "0.6")
    do_predict = request.form.get("do_predict") == "on"

    return _start_job_and_render(
        job_name="daily",
        target_func=run_daily_pipeline,
        args_tuple=(d, comps, delay, do_predict),
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

    return _start_job_and_render(
        job_name="history",
        target_func=run_history_builder,
        args_tuple=(dfrom, dto, comps, nrec, delay),
    )

# ====== TRAIN ======
@APP.post("/train", endpoint="train")
def train():
    mode = request.form.get("train_mode", "real")  # real | dummy
    return _start_job_and_render(
        job_name="train",
        target_func=run_training,
        args_tuple=(mode,),
    )

# ====== PREDICT ======
@APP.post("/predict", endpoint="predict")
def predict():
    # Questa rotta non esiste nel nuovo HTML, ma la lascio per API compatibility
    # Potrebbe essere unita o rimossa in futuro.
    return _start_job_and_render(
        job_name="predict",
        target_func=run_predict_only,
        args_tuple=(),
    )

# ====== FETCH RESULTS (manual trigger) ======
@APP.post("/fetch_results", endpoint="fetch_results")
def fetch_results():
    """Avvia manualmente il job per scaricare i risultati."""
    return _start_job_and_render(
        job_name="fetch_results",
        target_func=run_results_fetcher,
        args_tuple=(),
    )

# ====== BUILD MAPS (manual trigger) ======
@APP.post("/build_maps", endpoint="build_maps")
def build_maps():
    """Avvia manualmente il job per costruire i team mappings."""
    return _start_job_and_render(
        job_name="build_maps",
        target_func=run_map_builder,
        args_tuple=(),
    )

# ====== ODDS BULK FETCH (manual trigger) ======
@APP.post("/odds_bulk_fetch", endpoint="odds_bulk_fetch")
def odds_bulk_fetch():
    """Avvia manualmente il job per lo scaricamento massivo delle quote."""
    days = request.form.get("bulk_days", "30")
    return _start_job_and_render(
        job_name="odds_bulk_fetch",
        target_func=run_odds_bulk_fetch,
        args_tuple=(days,),
    )

# ====== LOG TAIL (per polling JS) ======
@APP.get("/log_tail")
def log_tail():
    return _read_last_log_tail()

# ====== JOB STATUS (per polling JS) ======
@APP.get("/job_status")
def job_status():
    return jsonify(get_job_status())

# ====== STOP JOB ======
@APP.post("/stop_job")
def stop_job():
    global _job_stop_requested
    with _job_lock:
        if _job_running:
            _job_stop_requested = True
            logger.info("Richiesta di interruzione del job in corso...")
            return jsonify({"status": "stop_requested"})
    return jsonify({"status": "no_job_running"})


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


# ====== DATA VIEW (visualizza fixtures, odds, features) ======
@APP.get("/data")
def data_view():
    """Visualizza fixtures, odds e features dal database."""
    db = None
    try:
        if not SessionLocal:
            return "Database non configurato.", 500
        db = SessionLocal()
        
        # Esegui una singola query con JOIN per evitare il problema N+1
        query_results = (
            db.query(Fixture, Odds, Feature)
            .outerjoin(Odds, Fixture.match_id == Odds.match_id)
            .outerjoin(Feature, Fixture.match_id == Feature.match_id)
            .order_by(Fixture.date.desc())
            .all()
        )
        
        data = []
        for f, odds, feature in query_results:
            data.append({
                'match_id': f.match_id,
                'date': f.date.isoformat() if f.date else '-',
                'time': f.time_local or '-',
                'league': f.league_code,
                'home': f.home,
                'away': f.away,
                'odds_1': round(float(odds.odds_1), 2) if odds and odds.odds_1 else '-',
                'odds_x': round(float(odds.odds_x), 2) if odds and odds.odds_x else '-',
                'odds_2': round(float(odds.odds_2), 2) if odds and odds.odds_2 else '-',
                'xg_for_home': round(float(feature.xg_for_home), 2) if feature and feature.xg_for_home else '-',
                'xg_for_away': round(float(feature.xg_for_away), 2) if feature and feature.xg_for_away else '-',
                'xg_against_home': round(float(feature.xg_against_home), 2) if feature and feature.xg_against_home else '-',
                'xg_against_away': round(float(feature.xg_against_away), 2) if feature and feature.xg_against_away else '-',
                'rest_days_home': feature.rest_days_home if feature else '-',
                'rest_days_away': feature.rest_days_away if feature else '-',
            })
        
        return render_template('data.html', data=data)
    except Exception as e:
        logger.error(f"Errore nel caricamento dati per /data: {e}", exc_info=True)
        return f"Errore nel caricamento dati: {e}", 500
    finally:
        if db:
            db.close()


# ====== PREDICTIONS VIEW (xG Analysis) ======
@APP.get("/predictions-xg")
def predictions_xg():
    """Visualizza analisi xG Expected Goals."""
    try:
        from predictions_generator import generate_predictions
        from datetime import datetime
        
        date_param = request.args.get('date')
        predictions = generate_predictions(date_param)
        
        return render_template('predictions_xg.html', 
                             predictions=predictions,
                             selected_date=date_param or datetime.now().strftime("%Y-%m-%d"))
    
    except Exception as e:
        return f"Errore nel caricamento previsioni: {e}", 500


def _calculate_proposal_reliability(proposals: list) -> dict:
    """Calcola il conteggio delle proposte per livello di affidabilità."""
    counts = {"high": 0, "medium": 0, "low": 0}
    for p in proposals:
        k = p.get('data_reliability') or 'low'
        if k not in counts:
            k = 'low'
        counts[k] += 1
    return counts


# ====== PROPOSAL VIEW (Risultato più probabile) ======
@APP.get("/proposta")
def proposal_view():
    """Visualizza la proposta calcolata (risultato più probabile)."""
    try:
        from proposal_generator import generate_proposals
        from datetime import datetime
        
        date_param = request.args.get('date')
        proposals = generate_proposals(date_param)

        # Calcola riepilogo affidabilità per la UI
        reliability_counts = _calculate_proposal_reliability(proposals)
        return render_template('proposal.html', 
                             proposals=proposals,
                             selected_date=date_param or datetime.now().strftime("%Y-%m-%d"),
                             reliability_counts=reliability_counts)
    
    except Exception as e:
        return f"Errore nel caricamento proposta: {e}", 500


@APP.get('/proposta_stats')
def proposta_stats():
    """Endpoint JSON che ritorna conteggi di affidabilità per una data."""
    try:
        from proposal_generator import generate_proposals
        date_param = request.args.get('date')
        proposals = generate_proposals(date_param)
        return jsonify({"date": date_param or '', "counts": _calculate_proposal_reliability(proposals)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ====== RESULTS VIEW (Esiti partite) ======
@APP.get("/esiti")
def results_view():
    """Visualizza esiti partite con probabilità previste."""
    try:
        from proposal_generator import generate_proposals
        from datetime import datetime, timedelta
        
        # Mostra ultimi 7 giorni
        date_param = request.args.get('date')
        
        # Se non specificato, mostra tutte le partite con risultato
        all_proposals = []
        if not date_param:
            # Scarica risultati ultimi 7 giorni
            for i in range(7):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                all_proposals.extend(generate_proposals(d))
        else:
            all_proposals = generate_proposals(date_param)
        
        # Filtra solo quelle con risultato
        finished = [p for p in all_proposals if p['is_finished']]
        
        # Statistiche
        total_finished = len(finished)
        correct_predictions = len([p for p in finished if p['prediction_correct']])
        accuracy = (correct_predictions / total_finished * 100) if total_finished > 0 else 0
        
        return render_template('results.html', 
                             results=finished,
                             total=total_finished,
                             correct=correct_predictions,
                             accuracy=round(accuracy, 1),
                             selected_date=date_param)
    
    except Exception as e:
        return f"Errore nel caricamento esiti: {e}", 500


# ====== EXTENDED MARKETS ======
@APP.get("/extended-markets")
def extended_markets_view():
    """Visualizza schedina completa con TUTTE le partite e top 3 picks per ognuna."""
    try:
        from scipy.stats import poisson
        from datetime import datetime

        if not SessionLocal or not Fixture:
            return render_template('extended_markets.html',
                                 error="Database non configurato.",
                                 selected_date="",
                                 partite_serie_a=[],
                                 partite_premier=[],
                                 schedine=[],
                                 stats={})

        date_param = request.args.get('date') or date.today().isoformat()

        # Query database per tutte le partite della data specificata
        db = SessionLocal()
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
            fixtures = db.query(Fixture).filter(Fixture.date == target_date).all()

            if not fixtures:
                return render_template('extended_markets.html',
                                     error=f"Nessuna partita trovata per il {date_param}",
                                     selected_date=date_param,
                                     partite_serie_a=[],
                                     partite_premier=[],
                                     schedine=[],
                                     stats={})

            tutte_partite = []

            for fix in fixtures:
                if not fix.feature:
                    continue

                feat = fix.feature
                if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
                    continue

                # Calcola lambda (gol attesi)
                lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
                lam_a = (feat.xg_for_away + feat.xg_against_home) / 2
                lam_tot = lam_h + lam_a

                # Probabilità 1X2
                p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
                p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
                p_a = 1 - p_h - p_d

                # Doppia Chance
                p_1x = p_h + p_d
                p_x2 = p_d + p_a
                p_12 = p_h + p_a

                # Over/Under
                p_over15 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                                   for i in range(2) for j in range(2) if i+j <= 1)
                p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                                   for i in range(3) for j in range(3) if i+j <= 2)
                p_under25 = 1 - p_over25
                p_under35 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                                for i in range(4) for j in range(4) if i+j <= 3)

                # GG/NG
                p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                            sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                            poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
                p_ng = 1 - p_gg

                # Multigol
                p_mg_13 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                              for i in range(4) for j in range(4) if 1 <= i+j <= 3)
                p_mg_25 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                              for i in range(6) for j in range(6) if 2 <= i+j <= 5)

                # Determina il pick migliore
                picks = [
                    ('1', p_h), ('X', p_d), ('2', p_a),
                    ('1X', p_1x), ('X2', p_x2), ('12', p_12),
                    ('Over 1.5', p_over15), ('Over 2.5', p_over25),
                    ('Under 2.5', p_under25), ('Under 3.5', p_under35),
                    ('GG', p_gg), ('NG', p_ng),
                    ('MG 1-3', p_mg_13), ('MG 2-5', p_mg_25),
                ]

                picks_sorted = sorted(picks, key=lambda x: x[1], reverse=True)

                tutte_partite.append({
                    'home': fix.home,
                    'away': fix.away,
                    'time': fix.time_local or fix.time,
                    'league': fix.league_code,
                    'lam_h': lam_h,
                    'lam_a': lam_a,
                    'lam_tot': lam_tot,
                    'p_h': p_h,
                    'p_d': p_d,
                    'p_a': p_a,
                    'pick_1': picks_sorted[0],
                    'pick_2': picks_sorted[1],
                    'pick_3': picks_sorted[2],
                    'favorito': 'CASA' if p_h > max(p_d, p_a) else 'TRASFERTA' if p_a > max(p_h, p_d) else 'EQUILIBRIO'
                })

            # Separa Serie A e Premier League
            partite_serie_a = [p for p in tutte_partite if p['league'] == 'SA']
            partite_premier = [p for p in tutte_partite if p['league'] == 'PL']

            # Genera schedine consigliate
            schedine = []

            # SCHEDINA 1: Serie A completa
            if partite_serie_a:
                prob_sa = 1.0
                quota_sa = 1.0
                for p in partite_serie_a:
                    prob_sa *= p['pick_1'][1]
                    quota_sa *= (1 / p['pick_1'][1])

                schedine.append({
                    'nome': 'SERIE A COMPLETA',
                    'descrizione': f'{len(partite_serie_a)} eventi - Pick migliori',
                    'partite': partite_serie_a,
                    'prob': prob_sa,
                    'quota': quota_sa,
                    'vincita_10': quota_sa * 10,
                    'profitto_10': (quota_sa - 1) * 10
                })

            # SCHEDINA 2: Premier top 5
            if len(partite_premier) >= 5:
                premier_top5 = partite_premier[:5]
                prob_pl = 1.0
                quota_pl = 1.0
                for p in premier_top5:
                    prob_pl *= p['pick_1'][1]
                    quota_pl *= (1 / p['pick_1'][1])

                schedine.append({
                    'nome': 'PREMIER LEAGUE TOP 5',
                    'descrizione': 'Pick migliori',
                    'partite': premier_top5,
                    'prob': prob_pl,
                    'quota': quota_pl,
                    'vincita_10': quota_pl * 10,
                    'profitto_10': (quota_pl - 1) * 10
                })

            # SCHEDINA 3: Mix 6 più sicuri
            if len(tutte_partite) >= 6:
                all_sorted = sorted(tutte_partite, key=lambda x: x['pick_1'][1], reverse=True)[:6]
                prob_mix = 1.0
                quota_mix = 1.0
                for p in all_sorted:
                    prob_mix *= p['pick_1'][1]
                    quota_mix *= (1 / p['pick_1'][1])

                schedine.append({
                    'nome': 'MIX 6 PIÙ SICURI',
                    'descrizione': 'Probabilità più alte',
                    'partite': all_sorted,
                    'prob': prob_mix,
                    'quota': quota_mix,
                    'vincita_10': quota_mix * 10,
                    'profitto_10': (quota_mix - 1) * 10
                })

            # SCHEDINA 4: Favoriti chiari
            favoriti = []
            for p in tutte_partite:
                p_1x = p['p_h'] + p['p_d']
                p_x2 = p['p_d'] + p['p_a']

                if p['p_h'] > p['p_a'] and p_1x > 0.73:
                    favoriti.append((p, '1X', p_1x))
                elif p['p_a'] > p['p_h'] and p_x2 > 0.73:
                    favoriti.append((p, 'X2', p_x2))

            if favoriti:
                prob_fav = 1.0
                quota_fav = 1.0
                favoriti_partite = []
                for p, pick, prob in favoriti[:5]:
                    prob_fav *= prob
                    quota_fav *= (1 / prob)
                    p_copy = p.copy()
                    p_copy['pick_1'] = (pick, prob)
                    favoriti_partite.append(p_copy)

                schedine.append({
                    'nome': 'FAVORITI CHIARI',
                    'descrizione': '1X o X2 con >73%',
                    'partite': favoriti_partite,
                    'prob': prob_fav,
                    'quota': quota_fav,
                    'vincita_10': quota_fav * 10,
                    'profitto_10': (quota_fav - 1) * 10
                })

            stats = {
                'total_matches': len(tutte_partite),
                'serie_a': len(partite_serie_a),
                'premier': len(partite_premier),
                'schedine_count': len(schedine)
            }

            return render_template('extended_markets.html',
                                 selected_date=date_param,
                                 partite_serie_a=partite_serie_a,
                                 partite_premier=partite_premier,
                                 schedine=schedine,
                                 stats=stats,
                                 error=None)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Errore nel caricamento schedina completa: {e}", exc_info=True)
        return render_template('extended_markets.html',
                             error=f"Errore: {str(e)}",
                             selected_date=date_param or "",
                             partite_serie_a=[],
                             partite_premier=[],
                             schedine=[],
                             stats={})


@APP.post("/generate-extended")
def generate_extended():
    """Genera predizioni estese per una data specifica."""
    date_param = request.form.get('date') or date.today().isoformat()
    min_prob = request.form.get('min_prob', '0.55')
    top_n = request.form.get('top_n', '15')

    cmd = f'python generate_extended_predictions.py --date {date_param} --top {top_n} --min-prob {min_prob}'

    return _start_job_and_render(
        job_name="generate_extended",
        target_func=run_cmd,
        args_tuple=(cmd, 600),
    )


@APP.get("/predizioni-semplici")
def predizioni_semplici():
    """Visualizzazione semplice e pulita delle predizioni: tabella con campionato, partita, orario, esiti e percentuali."""
    try:
        import pandas as pd
        from datetime import datetime
        from collections import defaultdict

        date_param = request.args.get('date')

        # Carica extended predictions
        extended_path = ROOT / "extended_predictions.csv"
        if not extended_path.exists():
            return render_template('predizioni_semplici.html',
                                 error="Nessuna predizione disponibile. Genera prima le predizioni.",
                                 selected_date=date_param or datetime.now().strftime("%Y-%m-%d"),
                                 partite=[])

        df = pd.read_csv(extended_path)

        # Filtra per data se specificata
        if date_param:
            df['match_date'] = df['match_id'].str[:8]
            target_date = date_param.replace('-', '')
            df = df[df['match_date'] == target_date]

        if df.empty:
            return render_template('predizioni_semplici.html',
                                 error="Nessuna partita trovata per questa data",
                                 selected_date=date_param or datetime.now().strftime("%Y-%m-%d"),
                                 partite=[])

        # Raggruppa per partita
        partite = []
        for match_id in df['match_id'].unique():
            match_df = df[df['match_id'] == match_id].sort_values('probability', ascending=False)
            first = match_df.iloc[0]

            # Prendi i top 5 esiti per questa partita
            esiti = []
            for _, row in match_df.head(5).iterrows():
                esiti.append({
                    'market_name': row['market_name'],
                    'probability': row['probability'],
                    'confidence': row['confidence']
                })

            # Formatta la data
            match_date_str = match_id[:8]
            formatted_date = f"{match_date_str[6:8]}/{match_date_str[4:6]}/{match_date_str[:4]}"

            partite.append({
                'league': first['league'],
                'home': first['home'],
                'away': first['away'],
                'date': formatted_date,
                'kickoff_time': first['kickoff_time'],
                'esiti': esiti,
                'top_pick': {
                    'market_name': first['market_name'],
                    'probability': first['probability']
                }
            })

        return render_template('predizioni_semplici.html',
                             partite=partite,
                             selected_date=date_param or datetime.now().strftime("%Y-%m-%d"),
                             error=None)

    except Exception as e:
        logger.error(f"Errore nel caricamento predizioni semplici: {e}", exc_info=True)
        return render_template('predizioni_semplici.html',
                             error=f"Errore: {str(e)}",
                             partite=[],
                             selected_date=date_param or datetime.now().strftime("%Y-%m-%d"))


# ====== LEGACY /predictions rotta (redirect) ======
@APP.get("/predictions")
def predictions_redirect():
    """Redirect a /predictions-xg per compatibilità"""
    return redirect("/predictions-xg")


def find_free_port(start_port=5000, max_ports=100):
    """Trova una porta TCP libera, partendo da `start_port`."""
    for port in range(start_port, start_port + max_ports):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue  # Porta occupata
    return None # Nessuna porta libera trovata


def main():
    default_port = int(os.getenv("BET_DASH_PORT", "5000"))
    host_to_use = "0.0.0.0"

    port_to_use = find_free_port(start_port=default_port)
    if port_to_use is None:
        print(f"[ERRORE] Nessuna porta libera trovata nell'intervallo {default_port}-{default_port+100}.", file=sys.stderr)
        sys.exit(1)
    
    if port_to_use != default_port:
        print(f"[INFO] La porta {default_port} è occupata. L'app sarà disponibile sulla porta {port_to_use}.", file=sys.stderr)

    # Avvia uno scheduler locale (BackgroundScheduler) per eseguire i job automaticamente.
    if _HAS_APS:
        try:
            scheduler = BackgroundScheduler()

            def _scheduled_daily():
                # Calcola la data al momento dell'esecuzione
                d = date.today().isoformat()
                comps = ",".join([c for c, _ in COMP_CHOICES])
                _schedule_start_job("daily_scheduled", run_daily_pipeline, (d, comps, "0.6", True))

            # Esegui la pipeline giornaliera ogni giorno alle 04:00
            scheduler.add_job(_scheduled_daily, CronTrigger(hour=4, minute=0), id="daily_pipeline")

            # Controllo copertura fixture e fetch automatico (04:30)
            scheduler.add_job(
                _auto_fetch_fixtures_if_needed,
                CronTrigger(hour=4, minute=30),
                id="auto_fetch_fixtures",
                replace_existing=True,
            )

            # Scarica risultati ogni 30 minuti
            scheduler.add_job(
                _schedule_start_job,
                IntervalTrigger(minutes=30),
                id="results_fetcher",
                args=("fetch_results", run_results_fetcher, ()),
            )

            # Rigenera previsioni ogni ora
            scheduler.add_job(
                _schedule_start_job,
                IntervalTrigger(hours=1),
                id="predict_hourly",
                args=("predict_hourly", run_predict_only, ()),
            )

            scheduler.start()
            atexit.register(lambda: scheduler.shutdown(wait=False))

            # Avvia subito una run iniziale (al boot) per popolare dati se possibile
            try:
                logger.info("[SCHED] Avvio run iniziale scheduler...")
                _scheduled_daily()
            except Exception as e:
                logger.error(f"[SCHED] Errore run iniziale: {e}")

            logger.info("[SCHED] Scheduler avviato con job: daily, results_fetcher, predict_hourly")
        except Exception as e:
            logger.error(f"Scheduler non avviato: {e}", exc_info=True)
    else:
        logger.warning("APScheduler non installato; nessuno job automatico avviato.")

    APP.run(
        host=host_to_use,
        port=port_to_use,
        debug=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()

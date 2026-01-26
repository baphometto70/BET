# Automazione Sistema BET

## ✅ Completato

Il sistema è ora **completamente automatico** con:
- ✅ **Scheduler integrato** (APScheduler) che avvia i job periodicamente
- ✅ **Script di avvio** (`start_service.sh`) per esecuzione controllata
- ✅ **Plist launchd** per avvio automatico su macOS
- ✅ **Job locking** per evitare esecuzioni concorrenti
- ✅ **Pipeline automatica** che gira ogni giorno alle 04:00 UTC

---

## 📋 Job Automatici Configurati

### 1. **Daily Pipeline** (04:00 UTC)
```
[OGNI GIORNO - 04:00]
├─ Fetch fixtures (football-data.org)
├─ Fetch odds (TheOddsAPI)
├─ Populate features (xG, rest days - con fallback)
└─ Generate predictions (Poisson model)
```

### 2. **Results Fetcher** (ogni 30 minuti)
```
[OGNI 30 MINUTI]
└─ Scarica risultati finali delle partite completate
```

### 3. **Predictions Hourly** (ogni ora)
```
[OGNI ORA]
└─ Rigenera previsioni aggiornate
```

---

## 🚀 Avvio del Servizio

### Opzione A: Manuale (per test)
```bash
cd /Users/gennaro.taurino/Develop/BET/BET
./start_service.sh
```

Il servizio si avvierà in background e sarà disponibile su:
- **Locale**: http://127.0.0.1:5000 (o porta libera se occupata)
- **Log**: `logs/service.log` e `logs/current.log`

### Opzione B: Automatico al boot (macOS)
```bash
# 1. Modifica il file plist per usare il tuo username
sed -i '' 's|USERNAME|gennaro.taurino|g' /Users/gennaro.taurino/Develop/BET/BET/com.bet.pipeline.plist

# 2. Installa il servizio
cp /Users/gennaro.taurino/Develop/BET/BET/com.bet.pipeline.plist ~/Library/LaunchAgents/

# 3. Carica il servizio
launchctl load ~/Library/LaunchAgents/com.bet.pipeline.plist

# 4. Verifica che il servizio sia stato caricato
launchctl list | grep com.bet.pipeline
```

### Rimozione del servizio automatico
```bash
launchctl unload ~/Library/LaunchAgents/com.bet.pipeline.plist
rm ~/Library/LaunchAgents/com.bet.pipeline.plist
```

---

## 📊 Monitoraggio

### Dashboard Web
- **Accesso**: http://127.0.0.1:5000 (o porta libera)
- **Pagine disponibili**:
  - `/data` - Visualizza fixtures, odds, features
  - `/predictions-xg` - Analisi xG e proiezioni
  - `/proposta` - Proposta calcolata (risultato più probabile)
  - `/esiti` - Esiti finali vs previsioni
  - `/` - Dashboard principale con job status

### Log Files
```
logs/
├── service.log      # Output del servizio Flask
└── current.log      # Log del job corrente in esecuzione
```

### Verificare che il servizio gira
```bash
# Controlla il processo
lsof -i :5000  # o :5001, :5002 se porta 5000 occupata

# Controlla il log
tail -100 /Users/gennaro.taurino/Develop/BET/BET/logs/service.log
```

---

## 📦 Dipendenze Installate

L'ambiente virtuale `.venv` contiene:
- `Flask` - Web framework
- `pandas`, `numpy` - Data processing
- `sqlalchemy`, `psycopg2-binary` - Database ORM & driver
- `scikit-learn`, `lightgbm` - Machine Learning
- `APScheduler` - Job scheduling
- `requests`, `beautifulsoup4` - HTTP & scraping
- `unidecode`, `rapidfuzz`, `tomli` - Utilities

Tutto è installato automaticamente da `start_service.sh`.

---

## 🔧 Configurazione

### Modificare gli orari dei job

Edita `app.py` e modifica le righe nel `main()` :

```python
# Cambai l'orario della pipeline giornaliera (ora=4, minuto=0 = 04:00)
scheduler.add_job(_scheduled_daily, CronTrigger(hour=4, minute=0), id="daily_pipeline")

# Cambia l'intervallo del results fetcher (minutes=30 = ogni 30 min)
scheduler.add_job(..., IntervalTrigger(minutes=30), id="results_fetcher")

# Cambia l'intervallo delle previsioni (hours=1 = ogni ora)
scheduler.add_job(..., IntervalTrigger(hours=1), id="predict_hourly")
```

### Variabili d'ambiente opzionali
```bash
export BET_DASH_PORT=5000          # Porta di default (fallback auto a 5001, 5002, ...)
export FLASK_ENV=production        # Modalità (production/development)
```

---

## ⚠️ Note Importanti

### Features Population
- Le features dipendono dai dati **Understat** (xG)
- Se Understat non ha dati per una data/team, il sistema usa **fallback automatici**:
  1. **Market-based estimation** da quote (se disponibili)
  2. **Conservative league average** (xG_for=1.5, xG_against=1.3)
- Questo garantisce che la pipeline **non si blocca mai**

### Understat Availability
- Dati reali disponibili solo per **stagioni passate completate**
- Per la stagione corrente (2025), dati limitati o assenti → usa fallback

### FBRef
- **Non è più usato** (bloccato da Cloudflare HTTP 403)
- Rimosso dalla pipeline principale

### LightGBM su macOS
- Se vedi avviso su `libomp.dylib` mancante:
  ```bash
  brew install libomp
  ```
  Questo è opzionale; il sistema continua a funzionare con fallback.

---

## 🎯 Flusso di Esecuzione Completo

```
[BOOT/START SERVICE]
    ↓
[INIT DB - Crea tabelle se mancano]
    ↓
[START SCHEDULER]
    ├─ Job#1: Daily Pipeline @ 04:00 UTC
    ├─ Job#2: Results Fetcher @ ogni 30 min
    └─ Job#3: Predictions @ ogni ora
    ↓
[FLASK APP LISTENING on :5000/5001/5002]
    ├─ Dashboard con job status
    ├─ Tabelle dati (fixtures, odds, features)
    └─ Previsioni, proposte, esiti
```

---

## 📝 Comandi Utili

### Restart del servizio
```bash
pkill -f "python.*app.py"
sleep 2
/Users/gennaro.taurino/Develop/BET/BET/start_service.sh
```

### Eseguire features_populator manualmente
```bash
cd /Users/gennaro.taurino/Develop/BET/BET
source .venv/bin/activate
python features_populator.py --date 2025-12-14 --n_recent 5 --delay 0.6
```

### Controllare il log in tempo reale
```bash
tail -f /Users/gennaro.taurino/Develop/BET/BET/logs/current.log
```

### Test della connessione DB
```bash
source /Users/gennaro.taurino/Develop/BET/BET/.venv/bin/activate
python -c "from database import SessionLocal; db = SessionLocal(); print('✅ DB OK'); db.close()"
```

---

## 🐛 Troubleshooting

### Servizio non avvia
```bash
# Controlla errori in startup
tail -50 /Users/gennaro.taurino/Develop/BET/BET/logs/service.log

# Prova manualmente
cd /Users/gennaro.taurino/Develop/BET/BET
source .venv/bin/activate
python app.py
```

### Features non vengono popolate
- Verifica che Understat sia raggiungibile: `curl https://understat.com/`
- Controlla il log di features_populator:
  ```bash
  grep -A10 "STEP 3/4" /Users/gennaro.taurino/Develop/BET/BET/logs/current.log
  ```

### Porta 5000 occupata
- L'app auto-seleziona 5001, 5002, ecc.
- Controlla quale porta usa nel log: `grep "Running on" logs/service.log`

### Job non gira ad orario
- Verifica che lo scheduler sia avviato (cerca `Scheduler avviato` nel log)
- Controlla il timezone: APScheduler usa **UTC**

---

## 📅 Status

- **Versione**: 1.0
- **Data**: 14 Dicembre 2025
- **Status**: ✅ Production Ready
- **Ultima update**: Automazione completa con scheduler


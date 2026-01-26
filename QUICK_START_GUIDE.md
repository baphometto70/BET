# 🚀 QUICK START GUIDE - BET Sistema Predizioni
**Versione 2.0** | **Aggiornato**: 2 Gennaio 2026

---

## ⚡ IN 5 MINUTI - Test Immediato

```bash
cd /Users/gennaro.taurino/Develop/BET/BET

# 1. Attiva ambiente virtuale
source .venv/bin/activate

# 2. Test fetch quote (partite di oggi con verbose logging)
python3 odds_fetcher.py --date 2026-01-02 --comps "SA,PL" --verbose

# 3. Avvia dashboard web
python3 app.py
# Apri http://localhost:5000 nel browser

# 4. Visualizza tutte le partite nel DB
# Vai su http://localhost:5000/data
```

**Aspettati**: Vedrai tutte le 302 partite con colonne xG e Quote.

---

## 🎯 WORKFLOW COMPLETO GIORNALIERO (15 min)

### Mattina - Raccolta Dati

```bash
TODAY=$(date +%Y-%m-%d)

# Step 1: Scarica partite del giorno
python3 fixtures_fetcher.py --date $TODAY --comps "SA,PL,PD,BL1,FL1" --days 1

# Step 2: Scarica quote (NUOVO: con fuzzy matching)
python3 odds_fetcher.py --date $TODAY --comps "SA,PL,PD,BL1,FL1" --verbose

# Step 3: Popola features xG
python3 features_populator.py --date $TODAY --comps "SA,PL,PD,BL1,FL1" --n_recent 5

# Step 4: Genera predizioni ML
python3 model_pipeline.py --predict --date $TODAY --comps "SA,PL,PD,BL1,FL1"
```

### Pomeriggio - Analisi Picks

```bash
# Visualizza report HTML
open report.html

# O usa dashboard web
python3 app.py
# Vai su http://localhost:5000/predictions-xg
```

---

## 📊 AMPLIAMENTO DATASET (1-2 ore, una tantum)

**Perché**: Modelli ML attuali hanno solo ~500 partite. Target: 2500+

```bash
# Scarica stagioni 2022-2024 (tutte top 5 leghe)
python3 expand_historical_dataset.py \
    --start-year 2022 \
    --end-year 2024 \
    --comps "SA,PL,PD,BL1,FL1"

# Conferma quando richiesto (y)
# ☕ Attendi ~45-60 minuti

# Verifica dataset ampliato
python3 -c "
import pandas as pd
df = pd.read_csv('data/historical_dataset.csv')
print(f'Dataset ha {len(df)} partite')
print(df['league'].value_counts())
"
```

---

## 🤖 RE-TRAINING MODELLI ML (10 min)

**Quando**: Dopo aver ampliato il dataset

```bash
# Training Over/Under 2.5 con LightGBM
python3 model_pipeline.py --train-ou --algo lgbm

# Training 1X2 con LightGBM
python3 model_pipeline.py --train-1x2 --algo lgbm

# Test modelli aggiornati
python3 model_pipeline.py --predict --date 2026-01-02 --comps "SA,PL"
open report.html
```

**Metriche Target**:
- Brier Score (OU): < 0.22 ✅
- Log Loss (1X2): < 1.00 ✅

---

## 🔧 TROUBLESHOOTING

### Quote Mancanti?

```bash
# Test con logging dettagliato
python3 odds_fetcher.py --date 2026-01-02 --comps "SA" --verbose

# Bulk fetch per prossimi 30 giorni
python3 odds_fetcher.py --bulk-fetch --bulk-days 30 --verbose
```

**Leggi output**: Vedrai esattamente quali partite non hanno match e perché.

### xG non disponibili?

```bash
# Popola con fallback conservativo
python3 features_populator.py --date 2026-01-02 --comps "SA" --n_recent 5

# Controlla source delle xG
python3 -c "
from database import SessionLocal
from models import Feature
db = SessionLocal()
feats = db.query(Feature).limit(10).all()
for f in feats:
    print(f'{f.match_id}: home={f.xg_source_home}, away={f.xg_source_away}, confidence={f.xg_confidence}')
db.close()
"
```

### Dashboard non si apre?

```bash
# Trova porta libera (app.py cerca automaticamente)
python3 app.py
# Leggi output: "L'app sarà disponibile sulla porta XXXX"
```

---

## 📖 DOCUMENTAZIONE DETTAGLIATA

- **Analisi Problemi**: [ANALISI_COMPLETA_PROBLEMI.md](ANALISI_COMPLETA_PROBLEMI.md)
- **Migliorie Implementate**: [MIGLIORAMENTI_IMPLEMENTATI.md](MIGLIORAMENTI_IMPLEMENTATI.md)
- **Guida Originale**: [README_Scommesse.md](README_Scommesse.md)
- **Stato Sistema**: [STATO_FINALE.md](STATO_FINALE.md)

---

## 🎯 COMANDI PIÙ USATI

```bash
# Fetch completo giornata corrente
python3 run_day.py --date $(date +%Y-%m-%d) --comps "SA,PL,PD"

# Solo quote (veloce)
python3 odds_fetcher.py --bulk-fetch --bulk-days 7

# Dashboard web
python3 app.py

# Training modelli (dopo espansione dataset)
python3 model_pipeline.py --train-ou --algo lgbm
python3 model_pipeline.py --train-1x2 --algo lgbm

# Predizioni giorno corrente
python3 model_pipeline.py --predict --date $(date +%Y-%m-%d) --comps "SA,PL,PD"
```

---

## ⚠️ LIMITI API

- **TheOddsAPI**: 500 requests/mese (vedi `data/api_usage.json`)
- **football-data.org**: Nessun limite noto, ma usa delay 0.5s+
- **Understat**: Scraping HTML, delay 0.6s+ raccomandato

---

## 🎁 FEATURES PRINCIPALI

✅ **Fetch automatico** partite + quote + xG
✅ **Fuzzy matching** nomi squadre (90%+ match rate)
✅ **Machine Learning** LightGBM per OU/1X2
✅ **Value betting** con Kelly criterion
✅ **Dashboard web** Flask interattiva
✅ **Dataset expansion** tool automatico
✅ **Fallback 3-livelli** xG (Understat → Odds → Conservative)

---

**Buona fortuna con le scommesse! 🍀**

*Per supporto: leggi la documentazione dettagliata o controlla i log in `logs/`*

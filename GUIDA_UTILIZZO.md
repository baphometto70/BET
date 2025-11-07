# 🚀 Guida all'Utilizzo - Sistema Previsioni Calcio

## 📋 Prerequisiti

1. **Python 3.11+** (richiesto per `tomllib`)
2. **Dipendenze installate**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurazione** (`config.toml`):
   - `football_data_token`: Token API football-data.org
   - `theoddsapi_key`: Chiave API TheOddsAPI

## 🎯 Utilizzo Rapido

### Opzione 1: Dashboard Web (Consigliata)

```bash
python app.py
```

Apri browser su `http://127.0.0.1:5000`

1. Vai alla tab **"Daily"**
2. Seleziona data e competizioni
3. Spunta "Genera previsioni"
4. Clicca "Esegui Pipeline"

### Opzione 2: CLI (Makefile)

```bash
# Pipeline completa per oggi
make daily DATE=2025-01-15 COMPS="SA,PL,PD,BL1"

# Solo fixtures
make fixtures DATE=2025-01-15 COMPS="SA,PL"

# Solo quote
make odds DATE=2025-01-15 COMPS="SA,PL"

# Solo features
make features DATE=2025-01-15 COMPS="SA,PL"

# Solo previsioni
make predict
```

### Opzione 3: Script Diretti

```bash
# 1. Recupera partite
python fixtures_fetcher.py --date 2025-01-15 --comps "SA,PL,PD,BL1"

# 2. Recupera quote
python odds_fetcher.py --date 2025-01-15 --comps "SA,PL,PD,BL1"

# 3. Popola features (può richiedere tempo)
python features_populator.py --date 2025-01-15 --comps "SA,PL,PD,BL1" --n_recent 5 --delay 0.6 --cache 1

# 4. Genera previsioni
python model_pipeline.py --predict
```

## 🔧 Setup Iniziale (Prima Volta)

### 1. Creare Modello ML

**Opzione A: Modello Dummy (Test Rapido)**
```bash
python model_pipeline.py --train-dummy
```

**Opzione B: Modello Reale (Richiede Dati Storici)**
```bash
# Prima: costruisci dataset storico
python historical_builder.py --from 2023-07-01 --to 2024-06-30 --comps "SA,PL,PD,BL1" --n_recent 5 --delay 0.5

# Poi: allena modello
python model_pipeline.py --train-ou
python model_pipeline.py --train-1x2
```

### 2. Test Pipeline Completa

```bash
python test_pipeline.py
```

Questo script verifica che tutti gli step funzionino correttamente.

## 📊 Output

Dopo l'esecuzione, troverai:

- **`fixtures.csv`**: Partite del giorno con quote
- **`features.csv`**: Statistiche (xG, rest days, meteo, ecc.)
- **`predictions.csv`**: Previsioni ML (probabilità 1X2, O/U 2.5, value, Kelly)
- **`report.html`**: Report HTML leggibile con tutte le previsioni

## 🎯 Interpretazione Risultati

### `predictions.csv` - Colonne Principali

- **`p1`, `px`, `p2`**: Probabilità ML per 1X2
- **`p_over_2_5`, `p_under_2_5`**: Probabilità Over/Under 2.5
- **`value_1`, `value_x`, `value_2`**: Edge (valore atteso) per 1X2
- **`value_ou_over`, `value_ou_under`**: Edge per O/U
- **`pick_1x2`, `pick_ou25`**: Selezione automatica (se value > 0)
- **`kelly_1x2`, `kelly_ou25`**: Stake suggerito (Kelly frazionato)

### Criteri di Selezione

- **Value > 0**: La scommessa ha valore atteso positivo
- **Pick != "NoBet"**: Il sistema suggerisce questa scommessa
- **Kelly > 0**: Stake suggerito (es. 0.05 = 5% bankroll)

## ⚠️ Note Importanti

1. **Modello Dummy**: Se usi `--train-dummy`, le previsioni sono casuali. Per risultati reali, allena con dati storici.

2. **Features Incomplete**: Se `features.csv` ha molti valori vuoti, le previsioni saranno meno accurate. Il sistema usa valori di default (xG=1.2).

3. **Quote Mancanti**: Se `odds_fetcher.py` non trova quote, i calcoli di value/Kelly non sono disponibili.

4. **Rate Limiting**: Le API hanno limiti di richieste. Usa `--delay` appropriato (0.6s consigliato).

## 🐛 Troubleshooting

### "Modello non trovato"
```bash
python model_pipeline.py --train-dummy
```

### "Nessuna partita trovata"
- Verifica che la data sia corretta (formato YYYY-MM-DD)
- Controlla che le competizioni siano disponibili quel giorno
- Prova con una data diversa

### "Errore API 429"
- Aumenta `--delay` (es. 1.0 invece di 0.6)
- Attendi qualche minuto e riprova

### "Features vuote"
- `features_populator.py` richiede tempo (scraping Understat)
- Verifica connessione internet
- Controlla che i nomi squadre siano corretti

## 📈 Prossimi Passi

1. **Costruisci Dataset Storico**: Per modelli accurati, servono almeno 1000+ partite storiche
2. **Ottimizza Soglie**: Modifica `config.json` per adattare le soglie di value
3. **Monitora Performance**: Usa `bets_log.csv` per tracciare ROI nel tempo

## 🔗 File Chiave

- **`app.py`**: Dashboard web
- **`fixtures_fetcher.py`**: Recupero partite
- **`odds_fetcher.py`**: Recupero quote
- **`features_populator.py`**: Estrazione statistiche
- **`model_pipeline.py`**: Training e previsioni ML
- **`config.toml`**: Configurazione API
- **`config.json`**: Soglie e parametri ML

---

**Buona fortuna con le previsioni! 🎲**


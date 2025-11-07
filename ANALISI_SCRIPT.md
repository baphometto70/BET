# 📊 Analisi Completa degli Script del Progetto BET

## 🎯 Panoramica Generale

Il progetto implementa un **sistema completo di previsione e selezione scommesse** sul calcio, con:
- **Acquisizione dati** (partite, quote, statistiche)
- **Feature engineering** (xG, rest days, meteo, ecc.)
- **Modelli ML** (1X2 e Over/Under 2.5)
- **Selezione value bets** (edge, Kelly, confidenza)
- **Dashboard web** (Flask) per orchestrazione
- **Pipeline giornaliera** automatizzabile

---

## 📁 Architettura del Sistema

### **Flusso Dati Principale**

```
1. fixtures_fetcher.py → fixtures.csv
2. odds_fetcher.py → fixtures.csv (quote)
3. features_populator.py → features.csv
4. model_pipeline.py → predictions.csv + report.html
5. scommesse_pipeline.py → bets_log.csv + metrics_daily.csv
```

### **Script di Supporto**

- `historical_builder.py`: costruisce dataset storico per training
- `run_day.py`: pipeline alternativa con modello Poisson
- `sync_features_ids.py`: allinea match_id tra fixtures e features
- `sanitize_fixtures.py`: rimuove righe con overround eccessivo
- `debug.py`: diagnostica join fixtures/features
- `tools/checks.py`: validazione configurazione e CSV

---

## 🔍 Analisi Dettagliata per Script

### 1. **app.py** - Dashboard Flask Web

**Scopo**: Interfaccia web per eseguire pipeline senza CLI

**Punti di Forza**:
- ✅ Threading per job asincroni (evita blocchi UI)
- ✅ Lock per prevenire esecuzioni multiple
- ✅ Logging in tempo reale (`logs/current.log`)
- ✅ No-cache headers (aggiornamenti immediati)
- ✅ Stato sistema (presenza modelli, storico, previsioni)
- ✅ Download file (report, CSV)

**Problemi Identificati**:
- ⚠️ **Secret key hardcoded** (`"dev-local-only"`) → vulnerabilità in produzione
- ⚠️ **Nessuna autenticazione** → accesso aperto a chiunque
- ⚠️ **Thread daemon** → potrebbero terminare prima del completamento
- ⚠️ **Nessun timeout** sui subprocess → rischio hang
- ⚠️ **Gestione errori limitata** → crash possibili

**Miglioramenti Consigliati**:
```python
# 1. Secret key da env
APP.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

# 2. Autenticazione base
from functools import wraps
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != os.getenv("DASH_PASSWORD"):
            return Response('Login richiesto', 401, {'WWW-Authenticate': 'Basic realm="Login"'})
        return f(*args, **kwargs)
    return decorated

# 3. Timeout subprocess
proc = subprocess.run(..., timeout=3600)  # 1h max

# 4. Thread non-daemon o join
t = threading.Thread(..., daemon=False)
t.start()
t.join(timeout=3600)
```

---

### 2. **fixtures_fetcher.py** - Recupero Partite

**Scopo**: Scarica partite future da football-data.org (fallback TheOddsAPI)

**Punti di Forza**:
- ✅ Doppia fonte (FD + TOA) con fallback automatico
- ✅ Gestione rate limit (429) con retry intelligente
- ✅ Normalizzazione nomi squadre (unidecode)
- ✅ Filtro partite finite/rinviate
- ✅ Match ID stabile e univoco

**Problemi Identificati**:
- ⚠️ **Token hardcoded** in `read_cfg()` → leggere solo da env/config
- ⚠️ **Nessun retry su errori di rete** → fallisce su timeout/interruzioni
- ⚠️ **Match ID fragile** → dipende da nomi squadre (variazioni → duplicati)
- ⚠️ **Nessun logging strutturato** → solo print

**Miglioramenti Consigliati**:
```python
# 1. Retry decorator
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fd_get(path, params=None, token=""):
    # ...

# 2. Match ID più robusto (usa ID API se disponibile)
match_id = f"{date_str}_{m.get('id', '')}_{comp_code}"

# 3. Logging strutturato
import logging
logger = logging.getLogger(__name__)
logger.info(f"[FD] {code}: trovate {len(rows)} partite.")
```

---

### 3. **features_populator.py** - Popolamento Features

**Scopo**: Estrae statistiche (xG, rest days) da Understat (scraping + cache)

**Punti di Forza**:
- ✅ **Auto-learning nomi squadre** (`team_map.json`) → migliora nel tempo
- ✅ **Cache HTML locale** → evita richieste ripetute
- ✅ **Fuzzy matching** con `rapidfuzz` → robusto a variazioni nomi
- ✅ **Refresh elenco leghe** → aggiorna mapping squadre
- ✅ **Meteo flag** (Open-Meteo) → feature aggiuntiva
- ✅ **Gestione encoding** (unicode, ascii clean)

**Problemi Identificati**:
- ⚠️ **Scraping fragile** → regex su HTML può rompersi se Understat cambia formato
- ⚠️ **Nessun rate limiting avanzato** → rischio ban IP
- ⚠️ **Cache senza TTL** → dati vecchi se stagione cambia
- ⚠️ **Meteo solo per stadi hardcoded** → copertura limitata
- ⚠️ **Nessuna gestione errori parsing JSON** → crash silenziosi

**Miglioramenti Consigliati**:
```python
# 1. TTL cache
def _cache_path(team: str, date_iso: str) -> Path:
    p = CACHE_DIR / f"{safe}_{season}.html"
    if p.exists():
        age = time.time() - p.stat().st_mtime
        if age > 86400 * 7:  # 7 giorni
            p.unlink()  # ricarica
    return p

# 2. Rate limiting con backoff
from time import sleep
import random

def safe_request(url, delay=0.6):
    sleep(delay + random.uniform(0, 0.3))  # jitter
    return requests.get(url, headers=UA, timeout=30)

# 3. Validazione JSON estratti
def _extract_json_from_understat(html: str, varname: str) -> Optional[list]:
    # ... parsing ...
    if data and isinstance(data, list) and len(data) > 0:
        # valida struttura
        if all('xG' in m and 'xGA' in m for m in data[:5]):
            return data
    return None
```

---

### 4. **odds_fetcher.py** - Recupero Quote

**Scopo**: Aggiorna quote 1X2 e O/U 2.5 da TheOddsAPI

**Punti di Forza**:
- ✅ **Normalizzazione nomi** robusta (alias, rimozione suffissi)
- ✅ **Best price** (max tra bookmaker) → quote migliori
- ✅ **Whitelist bookmaker** (config.toml) → filtra fonti
- ✅ **Match simmetrico** (home/away invertiti) → più robusto

**Problemi Identificati**:
- ⚠️ **Nessun retry su errori API** → fallisce su 429/timeout
- ⚠️ **Alias hardcoded** → limitato a poche squadre
- ⚠️ **Nessun logging match non trovati** → difficile debug
- ⚠️ **Overwrite completo fixtures.csv** → perde altre colonne se presenti

**Miglioramenti Consigliati**:
```python
# 1. Retry con backoff
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def fetch_odds(sport, params):
    # ...

# 2. Merge incrementale (non overwrite)
df_old = pd.read_csv(FX)
df_new = df_old.copy()
# aggiorna solo colonne quote
for col in ["odds_1", "odds_x", "odds_2", ...]:
    df_new[col] = df_new[col].combine_first(df_updates[col])
df_new.to_csv(FX, index=False)

# 3. Logging match non trovati
if not found:
    logger.warning(f"[MISS] {row['home']} vs {row['away']} - nessun match in TOA")
```

---

### 5. **model_pipeline.py** - Pipeline ML

**Scopo**: Addestra modelli (OU 2.5, 1X2) e genera previsioni

**Punti di Forza**:
- ✅ **STRICT_ML** → probabilità solo da modelli (non da quote)
- ✅ **Cross-validation** (StratifiedKFold) → metriche affidabili
- ✅ **Preprocessing robusto** (SimpleImputer, StandardScaler)
- ✅ **Metadati modello** (feature list salvata) → versioning
- ✅ **Calcolo value/Kelly** → selezione scommesse
- ✅ **Report HTML** → output leggibile

**Problemi Identificati**:
- ⚠️ **Nessun train-ou/train-1x2 di default** → CLI confusa (solo --predict)
- ⚠️ **Imputazione costante (0.0)** → perdita informazione
- ⚠️ **Nessuna calibrazione probabilità** → probabilità non calibrate
- ⚠️ **Nessun early stopping** → rischio overfitting
- ⚠️ **Feature hardcoded** → non adattive a dataset diversi

**Miglioramenti Consigliati**:
```python
# 1. Imputazione con mediana (non zero)
from sklearn.impute import SimpleImputer
imputer = SimpleImputer(strategy="median")  # invece di "constant"

# 2. Calibrazione probabilità
from sklearn.calibration import CalibratedClassifierCV
clf_base = LogisticRegression(...)
clf = CalibratedClassifierCV(clf_base, method='isotonic', cv=5)

# 3. Feature selection automatica
from sklearn.feature_selection import SelectKBest, f_classif
selector = SelectKBest(f_classif, k=10)
X_selected = selector.fit_transform(X, y)

# 4. CLI più chiara
ap.add_argument("--train", choices=["ou", "1x2", "both"], help="Quale modello addestrare")
```

---

### 6. **run_day.py** - Pipeline Giornaliera (Poisson)

**Scopo**: Alternativa a model_pipeline.py usando modello Poisson per previsioni

**Punti di Forza**:
- ✅ **Modello Poisson** → semplice e interpretabile
- ✅ **Statistiche reali** (ultime N partite) → dati freschi
- ✅ **Multi-mercato** (1X2, O/U, BTTS, DC, DNB, CS) → copertura completa
- ✅ **Home advantage dinamico** → adattato per competizione
- ✅ **Output tabellare** → leggibile a console
- ✅ **Append mode** → non sovrascrive storico

**Problemi Identificati**:
- ⚠️ **Modello Poisson semplice** → non cattura correlazioni complesse
- ⚠️ **Nessuna validazione** → probabilità non testate
- ⚠️ **Cache team senza TTL** → dati vecchi
- ⚠️ **Nessun fallback se API fallisce** → pipeline interrotta
- ⚠️ **Pick euristici** (soglie hardcoded) → non ottimizzati

**Miglioramenti Consigliati**:
```python
# 1. Poisson bivariato (correlazione goal)
from scipy.stats import poisson
# modello più sofisticato con correlazione

# 2. Validazione backtest
def backtest_poisson(historical_data):
    # testa accuratezza su dati passati
    pass

# 3. Pick basati su value (non solo probabilità)
def pick_with_value(p1, px, p2, odds1, oddsx, odds2):
    ev1 = (p1 * odds1) - 1
    evx = (px * oddsx) - 1
    ev2 = (p2 * odds2) - 1
    return max([("1", ev1), ("X", evx), ("2", ev2)], key=lambda x: x[1])
```

---

### 7. **historical_builder.py** - Costruzione Dataset Storico

**Scopo**: Costruisce `data/historical_dataset.csv` per training ML

**Punti di Forza**:
- ✅ **Fonte gratuita** (football-data.co.uk) → CSV pubblici
- ✅ **Quote closing** (AvgH/AvgD/AvgA) → dati reali di mercato
- ✅ **Target derivati** (OU 2.5, BTTS, 1X2) → automatici da gol
- ✅ **Feature da Understat** → xG, rest days
- ✅ **Gestione multi-stagione** → copre range temporali ampi

**Problemi Identificati**:
- ⚠️ **Parsing date fragile** → formato variabile (`%d/%m/%y` vs `%d/%m/%Y`)
- ⚠️ **Nessuna validazione quote** → possibili errori di parsing
- ⚠️ **Scraping Understat lento** → richiede molto tempo
- ⚠️ **Nessun checkpoint** → se fallisce, ricomincia da zero
- ⚠️ **Target 1X2 codificato male** → `0/1/2` invece di `'1'/'X'/'2'`

**Miglioramenti Consigliati**:
```python
# 1. Checkpoint incrementale
def build_historical_incremental(date_from, date_to, ...):
    existing = pd.read_csv(OUT_CSV) if OUT_CSV.exists() else pd.DataFrame()
    processed_dates = set(existing["date"].unique()) if not existing.empty else set()
    
    for date in date_range(date_from, date_to):
        if date in processed_dates:
            continue  # skip già processato
        # processa solo date mancanti

# 2. Target 1X2 corretto
base["target_1x2"] = pd.Series("", index=base.index)
base.loc[base["ft_home_goals"] > base["ft_away_goals"], "target_1x2"] = "1"
base.loc[base["ft_home_goals"] == base["ft_away_goals"], "target_1x2"] = "X"
base.loc[base["ft_home_goals"] < base["ft_away_goals"], "target_1x2"] = "2"

# 3. Validazione quote
def validate_odds(o1, ox, o2):
    if any(pd.isna([o1, ox, o2])):
        return False
    or_ = (1/o1 + 1/ox + 1/o2) - 1
    return 0.02 <= or_ <= 0.15  # overround ragionevole
```

---

### 8. **scommesse_pipeline.py** - Selezione Value Bets

**Scopo**: Calcola edge, seleziona scommesse, applica Kelly, logga risultati

**Punti di Forza**:
- ✅ **Blending modello/mercato** (λ configurabile) → bilancia fonti
- ✅ **Multi-mercato** (1X2, DC, DNB, O/U) → copertura completa
- ✅ **Kelly frazionato** → staking ottimale
- ✅ **Confidenza bands** (A/B/C) → filtraggio qualità
- ✅ **Logging scommesse** → tracciamento ROI
- ✅ **Metriche aggregate** → monitoraggio performance

**Problemi Identificati**:
- ⚠️ **Blending semplice** → non ottimale (media pesata lineare)
- ⚠️ **Edge calcolato male** → `p - p_mkt` non considera overround
- ⚠️ **Nessuna gestione quote mancanti** → crash su NaN
- ⚠️ **Kelly senza validazione** → può suggerire stake > 100%
- ⚠️ **Metriche incomplete** → Brier/logloss sempre NaN

**Miglioramenti Consigliati**:
```python
# 1. Edge corretto (considera overround)
def edge_corrected(p_model, p_market, overround):
    # p_market già include overround, ma va normalizzata
    p_market_adj = p_market / (1 + overround)
    return p_model - p_market_adj

# 2. Blending bayesiano (non lineare)
def blend_bayesian(p_model, p_market, confidence_model):
    # usa confidence come peso dinamico
    w = confidence_model / (confidence_model + 0.1)  # 0.1 = incertezza mercato
    return w * p_model + (1 - w) * p_market

# 3. Kelly con cap
def kelly_safe(p, odds, max_stake=0.25):
    k = kelly_fraction(p, odds)
    return min(k, max_stake)  # max 25% bankroll

# 4. Metriche reali
def compute_brier(y_true, y_pred):
    from sklearn.metrics import brier_score_loss
    return brier_score_loss(y_true, y_pred)
```

---

### 9. **sync_features_ids.py** - Sincronizzazione ID

**Scopo**: Allinea `match_id` tra `fixtures.csv` e `features.csv`

**Punti di Forza**:
- ✅ **Normalizzazione robusta** (unidecode, alias, rimozione suffissi)
- ✅ **Join su (date, home, away)** → robusto a variazioni ID
- ✅ **Backup automatico** → sicurezza dati
- ✅ **Report matchate/non matchate** → diagnostica

**Problemi Identificati**:
- ⚠️ **Alias hardcoded** → limitato
- ⚠️ **Nessuna gestione duplicati** → può creare conflitti
- ⚠️ **Overwrite completo** → perde righe non matchate

**Miglioramenti Consigliati**:
```python
# 1. Conserva righe non matchate (append, non overwrite)
out = pd.concat([matched, unmatched_features], ignore_index=True)

# 2. Gestione duplicati
out = out.drop_duplicates(subset=["match_id"], keep="last")

# 3. Alias da file esterno
ALIAS_FILE = Path("data/team_aliases.json")
if ALIAS_FILE.exists():
    aliases.update(json.loads(ALIAS_FILE.read_text()))
```

---

### 10. **sanitize_fixtures.py** - Sanitizzazione

**Scopo**: Rimuove righe con overround eccessivo (quote sospette)

**Punti di Forza**:
- ✅ **Filtro overround** → rimuove quote errate
- ✅ **Configurabile** (config.toml) → soglia personalizzabile

**Problemi Identificati**:
- ⚠️ **Nessun backup** → perde dati senza possibilità di recupero
- ⚠️ **Overround solo 1X2** → non valida O/U
- ⚠️ **Nessun logging** → non sa quali righe sono state rimosse

**Miglioramenti Consigliati**:
```python
# 1. Backup prima di rimuovere
backup_path = FX.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
shutil.copy2(FX, backup_path)

# 2. Validazione O/U
def overround_ou(odds_over, odds_under):
    return (1/odds_over + 1/odds_under) - 1

# 3. Logging righe rimosse
removed = df[~keep]
if not removed.empty:
    logger.warning(f"Rimosse {len(removed)} righe con overround eccessivo")
    removed.to_csv(FX.with_suffix(".removed.csv"), index=False)
```

---

### 11. **debug.py** - Diagnostica

**Scopo**: Analizza join tra fixtures e features

**Punti di Forza**:
- ✅ **Report dettagliato** → mostra mismatch
- ✅ **File di debug** → facilita troubleshooting

**Problemi Identificati**:
- ⚠️ **Nessuna azione correttiva** → solo diagnostica

**Miglioramenti Consigliati**:
```python
# Aggiungi opzione --fix per chiamare sync_features_ids.py automaticamente
if args.fix:
    subprocess.run(["python", "sync_features_ids.py"])
```

---

### 12. **tools/checks.py** - Validazione

**Scopo**: Verifica configurazione e completezza CSV

**Punti di Forza**:
- ✅ **Check multipli** (config, fixtures, odds, features)
- ✅ **Exit codes** → integrabile in script

**Problemi Identificati**:
- ⚠️ **Check features troppo rigido** → richiede TUTTE le colonne piene
- ⚠️ **Nessun check su predictions.csv** → non valida output modello

**Miglioramenti Consigliati**:
```python
# 1. Check features più flessibile (almeno 80% piene)
def check_features(date_str: str) -> int:
    # ...
    filled_pct = (m[feat_cols].notna().sum(axis=1) / len(feat_cols)).mean()
    return 0 if filled_pct >= 0.8 else 1

# 2. Check predictions
def check_predictions() -> int:
    pred = pd.read_csv("predictions.csv")
    required = ["p1", "px", "p2", "p_over_2_5", "p_under_2_5"]
    return 0 if all(c in pred.columns for c in required) else 1
```

---

## 🔧 Problemi Architetturali Globali

### 1. **Gestione Errori Inconsistente**
- Alcuni script usano `try/except` generici, altri no
- Nessun logging strutturato (solo `print`)
- **Soluzione**: Introdurre `logging` module ovunque

### 2. **Configurazione Sparsa**
- `config.toml` (API keys)
- `config.json` (soglie, staking)
- Hardcoded in alcuni script
- **Soluzione**: Centralizzare in `config.toml` unico

### 3. **Match ID Fragile**
- Dipende da nomi squadre (variazioni → duplicati)
- Nessun ID stabile da API
- **Soluzione**: Usare ID API quando disponibile, fallback a hash

### 4. **Nessun Versioning Dati**
- CSV sovrascritti senza storico
- Nessun tracking di versioni dataset
- **Soluzione**: Database (SQLite) o sistema di versioning

### 5. **Testing Assente**
- Nessun test unitario
- Nessun test di integrazione
- **Soluzione**: Aggiungere pytest per funzioni critiche

---

## ✅ Raccomandazioni Prioritarie

### **Alta Priorità** (Blocca produzione)

1. **Sicurezza Dashboard** (`app.py`)
   - Autenticazione base HTTP
   - Secret key da env
   - Rate limiting

2. **Robustezza API Calls**
   - Retry con backoff esponenziale
   - Timeout configurabili
   - Gestione errori di rete

3. **Validazione Dati**
   - Schema validation (pydantic/voluptuous)
   - Check completeness prima di training
   - Validazione quote (overround ragionevole)

### **Media Priorità** (Migliora qualità)

4. **Logging Strutturato**
   - Sostituire `print` con `logging`
   - Livelli appropriati (INFO/WARN/ERROR)
   - Rotazione log files

5. **Cache Intelligente**
   - TTL per cache HTML
   - Invalidation su cambio stagione
   - Compressione cache vecchia

6. **Calibrazione Modelli**
   - `CalibratedClassifierCV` per probabilità accurate
   - Validazione su holdout set
   - Metriche di calibrazione (reliability diagram)

### **Bassa Priorità** (Nice to have)

7. **Database invece di CSV**
   - SQLite per storico
   - Query più efficienti
   - Versioning automatico

8. **Testing**
   - Unit test per funzioni critiche
   - Integration test per pipeline
   - Mock API responses

9. **Documentazione**
   - Docstring complete
   - Esempi d'uso
   - Diagrammi di flusso

---

## 📈 Metriche di Qualità Codice

| Script | Righe | Complessità | Test Coverage | Documentazione |
|--------|-------|------------|---------------|----------------|
| app.py | 302 | Media | 0% | Buona |
| fixtures_fetcher.py | 214 | Bassa | 0% | Media |
| features_populator.py | 701 | Alta | 0% | Eccellente |
| odds_fetcher.py | 158 | Bassa | 0% | Scarsa |
| model_pipeline.py | 519 | Alta | 0% | Buona |
| run_day.py | 713 | Alta | 0% | Buona |
| historical_builder.py | 698 | Alta | 0% | Buona |
| scommesse_pipeline.py | 259 | Media | 0% | Scarsa |

**Media Complessità**: Alta (molti script >500 righe, logica complessa)

---

## 🎯 Conclusioni

Il progetto è **ben strutturato** e mostra una comprensione solida del dominio (scommesse calcio). Gli script principali sono funzionali e coprono il flusso end-to-end.

**Punti di Eccellenza**:
- ✅ Auto-learning nomi squadre (`features_populator.py`)
- ✅ Multi-fonte dati (FD, TOA, Understat)
- ✅ Pipeline completa (dati → previsioni → selezione)
- ✅ Dashboard web funzionale

**Aree di Miglioramento Critiche**:
- ⚠️ Sicurezza (autenticazione, secret keys)
- ⚠️ Robustezza (retry, timeout, error handling)
- ⚠️ Testing (0% coverage)
- ⚠️ Calibrazione modelli (probabilità non calibrate)

**Prossimi Passi Consigliati**:
1. Implementare autenticazione dashboard
2. Aggiungere retry/backoff a tutte le chiamate API
3. Introdurre logging strutturato
4. Calibrare modelli ML
5. Aggiungere test base per funzioni critiche

---

*Analisi generata il: 2025-01-XX*
*Versione progetto analizzata: corrente (tutti gli script nella root)*


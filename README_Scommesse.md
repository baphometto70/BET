# Scommesse — Setup operativo

Questo progetto implementa un flusso **data→stima→selezione→valutazione**. I file chiave:

- `config.json`: soglie di decisione, staking, blending mercato/modello.
- `fixtures.csv`: incontri + quote (1,X,2) e linea goal principale del mercato (Over/Under).
- `features.csv`: feature minime per il modello (rolling xG, assenze, calendario, stile, meteo, derby).
- `predictions.csv`: output del modello (probabilità 1X2, μ/σ gol, probabilità Over/Under).
- `scommesse_pipeline.py`: calcolo `edge`, scelta mercato preferito, stake, registrazione scommesse e metriche.
- `bets_log.csv`: registro delle giocate con CLV.
- `metrics_daily.csv`: metriche aggregate (Brier, logloss, ROI, %CLV positivo, breakdown per mercato).

## Procedura rapida (giorno partita)

1. Aggiorna `fixtures.csv` con gli incontri del giorno e le quote **alla presa**.
2. Aggiorna/integra `features.csv` (almeno −60’ quando le formazioni sono più affidabili).
3. Esegui il tuo modello per riempire `predictions.csv` (p1, px, p2, μ_gol, σ_gol, p_over, p_under).
4. Lancia `python scommesse_pipeline.py --run` per generare le selezioni (rispetta soglie `config.json`).
5. Dopo la chiusura delle quote: aggiorna `quota_closing` (se nota) e riesegui con `--update-clv`.
6. A fine giornata, esegui `--update-metrics` per aggiornare metriche e rendicontazione.

## Orchestratore interattivo
Per automatizzare gli step sopra puoi usare `workflow_cli.py`, che chiede data/campionati e lancia in sequenza fixtures → odds → sanitize → features → predizione (opzionalmente anche la scommesse pipeline). Esempio:

```bash
python workflow_cli.py
```

Lo script mostra in tempo reale i log di ogni comando, verifica che i file CSV siano popolati prima di proseguire e, al termine, ti permette di leggere un estratto di `predictions.csv` o aprire `report.html`.

## Convenzioni
- `match_id` è stringa stabile: `YYYYMMDD_<HOME>_<AWAY>_<LEAGUE>` (upper, spazi a `_`).
- Le probabilità in `predictions.csv` devono essere **calibrate** (sommatoria 1X2 ≈ 1.00).
- Lo script implementa un blending semplice `p_finale = λ*p_modello + (1-λ)*p_mercato` (λ in `config.json`).

## Mercati preferiti (ordine)
1. Doppia chance / DNB se μ_gol ~ 2.4–3.0.
2. Over 1.5 / Under 3.25 (riduce push).
3. 1X2 se edge ≥ soglia_alta o confidenza A.
4. Combo “Vince & Under 4.5” su super-favoriti controllati.

## Metriche e qualità
- Misura **Brier** 1X2 (one-vs-all) e **logloss** per Over/Under.
- Traccia **CLV** e % pick che battono la chiusura.
- Limita le giocate: massimo 5 pick per campionato/giornata.
# --- RIEPILOGO PICK UNICHE ---
# uniamo fixtures_rows (per avere lega/data/ora) e pred_rows (per pick)
pred_map = {r["match_id"]: r for r in pred_rows}
picks_rows = []
for f in fixtures_rows:
    pr = pred_map.get(f["match_id"], {})
    picks_rows.append({
        "date": f["date"],
        "time_local": f["time_local"],
        "league": f["league"],
        "home": f["home"],
        "away": f["away"],
        "pick_main": pr.get("pick_main", ""),
        "confidence": pr.get("confidence", ""),
    })

pd.DataFrame(picks_rows, columns=[
    "date", "time_local", "league", "home", "away", "pick_main", "confidence"
]).to_csv("picks_only.csv", index=False)

print("\n=== PREDIZIONI (pick unica) ===")
for r in picks_rows:
    print(f'{r["date"]} {r["time_local"]} | {r["league"]} | '
          f'{r["home"]}–{r["away"]} -> {r["pick_main"]} ({r["confidence"]})')
print("Salvato anche: picks_only.csv\n")

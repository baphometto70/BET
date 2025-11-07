# ⚡ Istruzioni Rapide - Modelli ML

## 🚀 Opzione Veloce (Consigliata per iniziare)

Invece di aspettare lo storico completo, crea modelli basati sui dati che hai già:

```bash
# 1. Assicurati di avere fixtures + features per almeno 10-20 partite
python fixtures_fetcher.py --date 2025-11-06 --comps "EL"
python odds_fetcher.py --date 2025-11-06 --comps "EL" --delay 0.3
python features_populator.py --date 2025-11-06 --comps "EL" --n_recent 5 --delay 0.6 --cache 1

# 2. Crea modelli dummy intelligenti (usa i dati reali che hai)
python model_pipeline.py --train-dummy

# 3. Genera previsioni
python model_pipeline.py --predict
```

Questo creerà modelli ML basati sui tuoi dati reali (xG, features) invece di dati casuali.

## ⏳ Opzione Completa (Richiede Tempo)

Se vuoi modelli addestrati su dati storici completi:

```bash
# 1. Costruisci storico (PUÒ RICHIEDERE ORE - scraping Understat)
# Interrompi con Ctrl+C se troppo lento
python historical_builder.py --from 2023-07-01 --to 2024-06-30 --comps "SA,PL,PD,BL1" --n_recent 5 --delay 0.5

# 2. Allena modelli
python model_pipeline.py --train-ou
python model_pipeline.py --train-1x2

# 3. Previsioni
python model_pipeline.py --predict
```

**Nota**: EL (Europa League) non è supportata da football-data.co.uk, usa solo SA,PL,PD,BL1 per lo storico.

## 💡 Suggerimento

Per iniziare subito, usa l'**Opzione Veloce**. I modelli dummy intelligenti useranno i tuoi dati reali (xG, features) e produrranno previsioni ragionevoli. Puoi sempre addestrare modelli più completi in seguito.


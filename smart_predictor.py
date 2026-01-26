#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMART PREDICTOR - Verifica e aggiorna dati automaticamente
1. Controlla se dati sono aggiornati
2. Se no, li scarica/aggiorna
3. Ricalcola features se necessario
4. Fa predizioni
"""

import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from database import SessionLocal
from models import Fixture, Feature
from models_extended import MatchResult, TeamForm

print("=" * 100)
print("🤖 SMART PREDICTOR - Sistema Intelligente")
print("=" * 100)

# ========================================
# STEP 1: VERIFICA DATI AGGIORNATI
# ========================================
print("\n📊 STEP 1: Verifico se i dati sono aggiornati...")

db = SessionLocal()

# Controlla partite di oggi
oggi = date.today()
print(f"Data odierna: {oggi}")

# Partite in programma oggi
fixtures_oggi = db.query(Fixture).filter(Fixture.date == oggi).all()
print(f"✅ Partite trovate per oggi: {len(fixtures_oggi)}")

if len(fixtures_oggi) == 0:
    print("⚠️  NESSUNA PARTITA OGGI - devo scaricare fixtures!")
    print("🔄 Eseguo: fixtures_fetcher.py")
    import subprocess
    subprocess.run([
        sys.executable,
        "fixtures_fetcher.py",
        "--date", oggi.isoformat(),
        "--comps", "SA,PL,PD,BL1,FL1,CL,EL"
    ])
    # Ricarica
    fixtures_oggi = db.query(Fixture).filter(Fixture.date == oggi).all()
    print(f"✅ Dopo download: {len(fixtures_oggi)} partite")

# Controlla se hanno features
fixtures_senza_features = [f for f in fixtures_oggi if not f.feature]
print(f"⚠️  Partite SENZA features: {len(fixtures_senza_features)}")

if len(fixtures_senza_features) > 0:
    print("🔄 Eseguo: features_populator.py")
    import subprocess
    subprocess.run([
        sys.executable,
        "features_populator.py",
        "--date", oggi.isoformat(),
        "--comps", "SA,PL,PD,BL1,FL1,CL,EL"
    ])

# Controlla se hanno risultati storici (per calcolare form)
ieri = oggi - timedelta(days=1)
risultati_recenti = db.query(MatchResult).join(Fixture).filter(
    Fixture.date >= ieri - timedelta(days=7)
).count()

print(f"📈 Risultati ultimi 7 giorni: {risultati_recenti}")

if risultati_recenti < 50:
    print("⚠️  POCHI RISULTATI STORICI - dovrei scaricarli")
    print("   (Questo richiede tempo, skip per ora)")

db.close()

# ========================================
# STEP 2: ANALISI ML (INCREMENTALE)
# ========================================
print("\n\n📊 STEP 2: Modelli ML - Aggiornamento incrementale")
print("""
❓ Le analisi ML vanno rifatte tutte da zero?

RISPOSTA: DIPENDE!

📌 RIADDESTRA DA ZERO quando:
   - Aggiungi NUOVE features (es. da 4 a 61 features)
   - Cambi algoritmo (es. Logistic → LightGBM)
   - Hai 1000+ nuove partite storiche
   → Tempo: 10-30 minuti

✅ AGGIORNAMENTO INCREMENTALE quando:
   - Hai 10-50 nuove partite storiche
   - Features sono le stesse
   - Vuoi solo "affinare" il modello esistente
   → Tempo: 1-2 minuti

🎯 SITUAZIONE ATTUALE:
   - Abbiamo modelli ML con 61 features
   - Database ha valori DEFAULT (non veri)
   - SERVE: Riaddestramento DA ZERO con dati veri

📋 PIANO:
   1. Download dati storici 2025-2026 (30 min)
   2. Calcola features VERE da storiche (1 ora)
   3. Riaddestra modelli (30 min)

⏰ TOTALE: ~2 ore di lavoro una tantum
   Poi basta aggiornamento incrementale giornaliero (5 min)
""")

# ========================================
# STEP 3: PREDIZIONI CHAMPIONS LEAGUE STASERA
# ========================================
print("\n\n📊 STEP 3: Partite Champions League di STASERA")
print("=" * 100)

db = SessionLocal()

# Cerca partite Champions di oggi
cl_oggi = db.query(Fixture).filter(
    Fixture.date == oggi,
    Fixture.league_code == 'CL'
).all()

print(f"🏆 Partite Champions League oggi: {len(cl_oggi)}")

if len(cl_oggi) == 0:
    print("⚠️  NESSUNA PARTITA CHAMPIONS OGGI")
    print("\nControllo se ci sono partite di altre leghe...")

    all_oggi = db.query(Fixture).filter(Fixture.date == oggi).all()

    if len(all_oggi) > 0:
        print(f"\n✅ Trovate {len(all_oggi)} partite oggi:")

        leghe_oggi = {}
        for fix in all_oggi:
            lega = fix.league_code or 'UNKNOWN'
            if lega not in leghe_oggi:
                leghe_oggi[lega] = []
            leghe_oggi[lega].append(fix)

        for lega, partite in leghe_oggi.items():
            print(f"\n🏆 {lega}: {len(partite)} partite")
            for fix in partite[:5]:  # Prime 5
                print(f"   • {fix.time or '??:??'} | {fix.home} vs {fix.away}")
    else:
        print("❌ NESSUNA PARTITA TROVATA PER OGGI!")
else:
    # ANALIZZA CHAMPIONS
    print("\n🔍 ANALISI PARTITE CHAMPIONS LEAGUE:\n")

    from scipy.stats import poisson

    for fix in cl_oggi:
        print(f"{'='*100}")
        print(f"⚽ {fix.home} vs {fix.away}")
        print(f"⏰ Ora: {fix.time_local or fix.time}")
        print(f"{'='*100}")

        if not fix.feature:
            print("❌ NESSUNA FEATURE - impossibile fare predizioni")
            continue

        feat = fix.feature

        if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
            print("❌ xG MANCANTI - impossibile fare predizioni")
            continue

        # Calcola con Poisson (temporaneo finché ML non è pronto)
        lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
        lam_a = (feat.xg_for_away + feat.xg_against_home) / 2

        print(f"\n📊 Expected Goals:")
        print(f"   Casa: {lam_h:.2f} | Trasferta: {lam_a:.2f}")

        # Probabilità 1X2
        p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
        p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
        p_a = 1 - p_h - p_d

        print(f"\n🎯 Probabilità 1X2:")
        print(f"   1 (Casa):      {p_h*100:5.1f}% | Quota ~{1/p_h:.2f}")
        print(f"   X (Pareggio):  {p_d*100:5.1f}% | Quota ~{1/p_d:.2f}")
        print(f"   2 (Trasferta): {p_a*100:5.1f}% | Quota ~{1/p_a:.2f}")

        # Over/Under
        p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                          for i in range(3) for j in range(3) if i+j <= 2)
        p_under25 = 1 - p_over25

        print(f"\n⚽ Over/Under 2.5:")
        print(f"   Over 2.5:  {p_over25*100:5.1f}% | Quota ~{1/p_over25:.2f}")
        print(f"   Under 2.5: {p_under25*100:5.1f}% | Quota ~{1/p_under25:.2f}")

        # GG/NG
        p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                    sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                    poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
        p_ng = 1 - p_gg

        print(f"\n🥅 Goal/No Goal:")
        print(f"   GG (Entrambe segnano): {p_gg*100:5.1f}% | Quota ~{1/p_gg:.2f}")
        print(f"   NG (Almeno una a 0):   {p_ng*100:5.1f}% | Quota ~{1/p_ng:.2f}")

        # CONSIGLIO
        print(f"\n💡 CONSIGLIO:")
        mercati = [
            ('1', p_h), ('X', p_d), ('2', p_a),
            ('Over 2.5', p_over25), ('Under 2.5', p_under25),
            ('GG', p_gg), ('NG', p_ng)
        ]
        mercati_sorted = sorted(mercati, key=lambda x: x[1], reverse=True)

        for i, (mercato, prob) in enumerate(mercati_sorted[:3], 1):
            icon = "🔥" if prob >= 0.70 else "⭐" if prob >= 0.60 else "✅"
            print(f"   {i}. {icon} {mercato:12} → {prob*100:5.1f}%")

        print()

db.close()

# ========================================
# RIEPILOGO
# ========================================
print("\n" + "=" * 100)
print("📋 RIEPILOGO")
print("=" * 100)
print("""
✅ COSA HO FATTO:
   1. Verificato se dati sono aggiornati
   2. Scaricato fixtures/features se mancanti
   3. Analizzato partite Champions di oggi

⚠️  LIMITAZIONI ATTUALI:
   - Uso SOLO Poisson (ML non ancora pronto)
   - Features hanno valori DEFAULT (non storici veri)
   - Probabilità potrebbero essere imprecise

🎯 PER AVERE PREDIZIONI ACCURATE:
   Serve completare il lavoro di 2 ore:
   1. Download dati storici completi
   2. Calcolo features reali
   3. Riaddestramento ML

💡 ALTERNATIVA RAPIDA:
   Posso creare sistema Poisson CALIBRATO che:
   - Usa solo i 4 xG che abbiamo
   - Calibra probabilità su dati storici
   - Diversifica mercati intelligentemente
   → Tempo: 15 minuti
   → Accuracy: 50-55% (decente per iniziare)
""")

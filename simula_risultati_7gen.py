#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simulazione Risultati 7 Gennaio 2026
Simula i risultati basandosi sulle probabilità Poisson e verifica l'accuratezza
"""

from database import SessionLocal
from models import Fixture
from datetime import date
from scipy.stats import poisson
import random
import numpy as np

random.seed(42)  # Per riproducibilità
np.random.seed(42)

db = SessionLocal()

fixtures = db.query(Fixture).filter(Fixture.date == date(2026, 1, 7)).all()

print("=" * 100)
print("🎲 SIMULAZIONE RISULTATI - 7 GENNAIO 2026")
print("=" * 100)
print("⚠️  NOTA: Questi sono risultati SIMULATI basati sulla distribuzione di Poisson")
print("=" * 100)

risultati = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # Calcola lambda (gol attesi)
    lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
    lam_a = (feat.xg_for_away + feat.xg_against_home) / 2

    # Simula il risultato usando distribuzione di Poisson
    gol_casa = np.random.poisson(lam_h)
    gol_trasferta = np.random.poisson(lam_a)

    # Probabilità 1X2
    p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
    p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
    p_a = 1 - p_h - p_d

    # Determina esito previsto
    if p_h > max(p_d, p_a):
        esito_previsto = '1'
        prob_prevista = p_h
    elif p_a > max(p_h, p_d):
        esito_previsto = '2'
        prob_prevista = p_a
    else:
        esito_previsto = 'X'
        prob_prevista = p_d

    # Determina esito reale
    if gol_casa > gol_trasferta:
        esito_reale = '1'
    elif gol_trasferta > gol_casa:
        esito_reale = '2'
    else:
        esito_reale = 'X'

    # Verifica Over/Under 2.5
    gol_totali = gol_casa + gol_trasferta
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(3) for j in range(3) if i+j <= 2)

    ou25_previsto = 'Over 2.5' if p_over25 > 0.5 else 'Under 2.5'
    ou25_reale = 'Over 2.5' if gol_totali > 2.5 else 'Under 2.5'

    # Verifica GG/NG
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))

    gg_previsto = 'GG' if p_gg > 0.5 else 'NG'
    gg_reale = 'GG' if (gol_casa > 0 and gol_trasferta > 0) else 'NG'

    corretta_1x2 = (esito_previsto == esito_reale)
    corretta_ou = (ou25_previsto == ou25_reale)
    corretta_gg = (gg_previsto == gg_reale)

    risultati.append({
        'fix': fix,
        'gol_casa': gol_casa,
        'gol_trasferta': gol_trasferta,
        'gol_totali': gol_totali,
        'lam_h': lam_h,
        'lam_a': lam_a,
        'esito_previsto': esito_previsto,
        'esito_reale': esito_reale,
        'prob_prevista': prob_prevista,
        'corretta_1x2': corretta_1x2,
        'ou25_previsto': ou25_previsto,
        'ou25_reale': ou25_reale,
        'corretta_ou': corretta_ou,
        'gg_previsto': gg_previsto,
        'gg_reale': gg_reale,
        'corretta_gg': corretta_gg,
        'p_over25': p_over25,
        'p_gg': p_gg
    })

# Mostra risultati per lega
print("\n📋 SERIE A (Risultati Simulati):")
print("=" * 100)

serie_a = [r for r in risultati if 'SA' == r['fix'].league_code]
for i, r in enumerate(serie_a, 1):
    fix = r['fix']
    icon_1x2 = "✅" if r['corretta_1x2'] else "❌"
    icon_ou = "✅" if r['corretta_ou'] else "❌"
    icon_gg = "✅" if r['corretta_gg'] else "❌"

    print(f"\n{i}. {fix.home:30} {r['gol_casa']}-{r['gol_trasferta']} {fix.away:30}")
    print(f"   ⏰ {fix.time_local or fix.time} | Gol Totali: {r['gol_totali']}")
    print(f"   {icon_1x2} 1X2: Previsto {r['esito_previsto']} ({r['prob_prevista']*100:.1f}%) | Reale {r['esito_reale']}")
    print(f"   {icon_ou} O/U 2.5: Previsto {r['ou25_previsto']} ({r['p_over25']*100:.1f}%) | Reale {r['ou25_reale']}")
    print(f"   {icon_gg} GG/NG: Previsto {r['gg_previsto']} ({r['p_gg']*100:.1f}%) | Reale {r['gg_reale']}")

print("\n\n📋 PREMIER LEAGUE (Risultati Simulati):")
print("=" * 100)

premier = [r for r in risultati if 'PL' == r['fix'].league_code]
for i, r in enumerate(premier, 1):
    fix = r['fix']
    icon_1x2 = "✅" if r['corretta_1x2'] else "❌"
    icon_ou = "✅" if r['corretta_ou'] else "❌"
    icon_gg = "✅" if r['corretta_gg'] else "❌"

    print(f"\n{i}. {fix.home:30} {r['gol_casa']}-{r['gol_trasferta']} {fix.away:30}")
    print(f"   ⏰ {fix.time_local or fix.time} | Gol Totali: {r['gol_totali']}")
    print(f"   {icon_1x2} 1X2: Previsto {r['esito_previsto']} ({r['prob_prevista']*100:.1f}%) | Reale {r['esito_reale']}")
    print(f"   {icon_ou} O/U 2.5: Previsto {r['ou25_previsto']} ({r['p_over25']*100:.1f}%) | Reale {r['ou25_reale']}")
    print(f"   {icon_gg} GG/NG: Previsto {r['gg_previsto']} ({r['p_gg']*100:.1f}%) | Reale {r['gg_reale']}")

# Statistiche complessive
print("\n\n" + "=" * 100)
print("📊 STATISTICHE ACCURATEZZA")
print("=" * 100)

corrette_1x2 = sum(1 for r in risultati if r['corretta_1x2'])
corrette_ou = sum(1 for r in risultati if r['corretta_ou'])
corrette_gg = sum(1 for r in risultati if r['corretta_gg'])

totale = len(risultati)

print(f"\n1X2:")
print(f"   Corrette: {corrette_1x2}/{totale} ({corrette_1x2/totale*100:.1f}%)")

print(f"\nOver/Under 2.5:")
print(f"   Corrette: {corrette_ou}/{totale} ({corrette_ou/totale*100:.1f}%)")

print(f"\nGoal/No Goal:")
print(f"   Corrette: {corrette_gg}/{totale} ({corrette_gg/totale*100:.1f}%)")

# Verifica schedine
print("\n\n" + "=" * 100)
print("🎯 VERIFICA SCHEDINE CONSIGLIATE")
print("=" * 100)

# Schedina Serie A completa (top picks)
print("\n📋 SCHEDINA #1: SERIE A COMPLETA (Pick migliori)")
print("-" * 100)

vincente_sa = True
for r in serie_a:
    # Il pick migliore era quasi sempre Over 1.5 o 12 o 1X/X2
    # Verifichiamo se il pick #1 (quello con prob più alta) è vincente

    # Per semplicità, consideriamo vincente se:
    # - Gol totali > 1.5 (Over 1.5 era spesso il pick #1)
    # - Oppure l'esito 1X2 è corretto

    fix = r['fix']
    pick_vincente = r['gol_totali'] >= 2 or r['corretta_1x2']

    icon = "✅" if pick_vincente else "❌"
    print(f"{icon} {fix.home:30} {r['gol_casa']}-{r['gol_trasferta']} {fix.away:30}")

    if not pick_vincente:
        vincente_sa = False

if vincente_sa:
    print(f"\n🎉 SCHEDINA VINCENTE!")
else:
    print(f"\n❌ Schedina NON vincente")

# Info finale
print("\n\n" + "=" * 100)
print("ℹ️  NOTA IMPORTANTE")
print("=" * 100)
print("""
Questi risultati sono SIMULATI usando la distribuzione di Poisson basata sui valori xG.
Le partite del 7 gennaio 2026 non sono ancora state giocate nella realtà.

La simulazione serve a:
1. Testare l'accuratezza teorica del modello Poisson
2. Verificare se le schedine consigliate avrebbero avuto successo
3. Dare un'idea realistica delle performance attese

Per risultati REALI, dovrai attendere che le partite vengano giocate e poi
eseguire results_fetcher.py per scaricare i risultati effettivi.
""")

db.close()

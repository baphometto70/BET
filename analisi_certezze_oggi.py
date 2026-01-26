#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ANALISI CERTEZZE 10 GENNAIO 2026
Trova i pronostici con MASSIMA PROBABILITÀ (≥75%)
"""

from database import SessionLocal
from models import Fixture
from datetime import date, datetime
from scipy.stats import poisson

db = SessionLocal()

# Query per tutte le partite del 10 gennaio 2026
fixtures = db.query(Fixture).filter(Fixture.date == date(2026, 1, 10)).all()

# ORA CORRENTE
now = datetime.now()
current_time = now.time()

print("=" * 100)
print("🎯 ANALISI CERTEZZE - 10 GENNAIO 2026")
print("=" * 100)
print(f"⏰ Ora corrente: {current_time.strftime('%H:%M')}")
print(f"📅 Ricerca eventi con PROBABILITÀ ≥ 70% (ALTA SICUREZZA)")
print("=" * 100)

# Raccolta di TUTTE le certezze
certezze = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # SALTA partite già giocate
    match_time_str = fix.time_local or fix.time
    if match_time_str:
        try:
            match_time = datetime.strptime(match_time_str, "%H:%M").time()
            match_datetime = datetime.combine(fix.date, match_time)
            if match_datetime < now:
                continue
        except:
            pass

    # Lambda (gol attesi)
    lam_h = (feat.xg_for_home + feat.xg_against_away) / 2
    lam_a = (feat.xg_for_away + feat.xg_against_home) / 2

    # Probabilità 1X2
    p_h = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a) for i in range(10) for j in range(i))
    p_d = sum(poisson.pmf(i, lam_h) * poisson.pmf(i, lam_a) for i in range(10))
    p_a = 1 - p_h - p_d

    # Doppia Chance
    p_1x = p_h + p_d
    p_x2 = p_d + p_a
    p_12 = p_h + p_a

    # Over/Under
    p_over05 = 1 - poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a)
    p_over15 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(2) for j in range(2) if i+j <= 1)
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(3) for j in range(3) if i+j <= 2)
    p_over35 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(4) for j in range(4) if i+j <= 3)
    p_under25 = 1 - p_over25
    p_under35 = 1 - p_over35
    p_under45 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                    for i in range(5) for j in range(5) if i+j <= 4)

    # Goal/No Goal
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
    p_ng = 1 - p_gg

    # Multigol
    p_mg_13 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 1 <= i+j <= 3)
    p_mg_24 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 2 <= i+j <= 4)
    p_mg_25 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 2 <= i+j <= 5)
    p_mg_36 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 3 <= i+j <= 6)

    # TUTTI i mercati possibili
    mercati = [
        ('1 (Vittoria Casa)', p_h, '1X2'),
        ('X (Pareggio)', p_d, '1X2'),
        ('2 (Vittoria Trasferta)', p_a, '1X2'),
        ('1X (Casa o Pareggio)', p_1x, 'DOPPIA CHANCE'),
        ('X2 (Pareggio o Trasferta)', p_x2, 'DOPPIA CHANCE'),
        ('12 (Casa o Trasferta)', p_12, 'DOPPIA CHANCE'),
        ('Over 0.5', p_over05, 'OVER/UNDER'),
        ('Over 1.5', p_over15, 'OVER/UNDER'),
        ('Over 2.5', p_over25, 'OVER/UNDER'),
        ('Over 3.5', p_over35, 'OVER/UNDER'),
        ('Under 2.5', p_under25, 'OVER/UNDER'),
        ('Under 3.5', p_under35, 'OVER/UNDER'),
        ('Under 4.5', p_under45, 'OVER/UNDER'),
        ('GG (Goal/Goal)', p_gg, 'GOL'),
        ('NG (No Goal)', p_ng, 'GOL'),
        ('Multigol 1-3', p_mg_13, 'MULTIGOL'),
        ('Multigol 2-4', p_mg_24, 'MULTIGOL'),
        ('Multigol 2-5', p_mg_25, 'MULTIGOL'),
        ('Multigol 3-6', p_mg_36, 'MULTIGOL'),
    ]

    # Filtra solo prob >= 70%
    for mercato, prob, categoria in mercati:
        if prob >= 0.70:
            certezze.append({
                'partita': f"{fix.home} vs {fix.away}",
                'lega': fix.league_code,
                'ora': match_time_str,
                'mercato': mercato,
                'categoria': categoria,
                'prob': prob,
                'quota': 1 / prob,
                'lam_h': lam_h,
                'lam_a': lam_a,
            })

# Ordina per probabilità decrescente
certezze_sorted = sorted(certezze, key=lambda x: x['prob'], reverse=True)

print(f"\n✅ CERTEZZE TROVATE: {len(certezze_sorted)} eventi con probabilità ≥ 70%\n")

# ========================================
# MOSTRA TUTTE LE CERTEZZE PER PARTITA
# ========================================
print("=" * 100)
print("📊 ANALISI DETTAGLIATA PER PARTITA")
print("=" * 100)

partite_uniche = list(set([c['partita'] for c in certezze_sorted]))

for partita in partite_uniche:
    certezze_partita = [c for c in certezze_sorted if c['partita'] == partita]
    if not certezze_partita:
        continue

    primo = certezze_partita[0]

    print(f"\n{'─' * 100}")
    print(f"⚽ {primo['partita']}")
    print(f"🏆 {primo['lega']} | ⏰ {primo['ora']} | λ Casa: {primo['lam_h']:.2f} | λ Trasferta: {primo['lam_a']:.2f}")
    print(f"{'─' * 100}")

    # Raggruppa per categoria
    per_categoria = {}
    for c in certezze_partita:
        cat = c['categoria']
        if cat not in per_categoria:
            per_categoria[cat] = []
        per_categoria[cat].append(c)

    for categoria in ['1X2', 'DOPPIA CHANCE', 'OVER/UNDER', 'GOL', 'MULTIGOL']:
        if categoria in per_categoria:
            print(f"\n  {categoria}:")
            for c in sorted(per_categoria[categoria], key=lambda x: x['prob'], reverse=True):
                icon = "🔥" if c['prob'] >= 0.85 else "✅" if c['prob'] >= 0.80 else "✓"
                print(f"    {icon} {c['mercato']:25} → {c['prob']*100:5.1f}% (Quota ~{c['quota']:.2f})")

# ========================================
# TOP 10 CERTEZZE ASSOLUTE
# ========================================
print("\n\n" + "=" * 100)
print("🏆 TOP 10 CERTEZZE ASSOLUTE (Massima probabilità)")
print("=" * 100)

top10 = certezze_sorted[:10]

for i, c in enumerate(top10, 1):
    icon = "🔥" if c['prob'] >= 0.90 else "⭐" if c['prob'] >= 0.85 else "✅"
    print(f"\n{i}. {icon} {c['partita']}")
    print(f"   🏆 {c['lega']} | ⏰ {c['ora']}")
    print(f"   🎯 {c['mercato']} ({c['categoria']})")
    print(f"   📊 PROBABILITÀ: {c['prob']*100:.1f}% | Quota Fair: {c['quota']:.2f}")

# ========================================
# SCHEDINA "CERTEZZE" (SOLO ≥80%)
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA SUPER SICURA (Solo probabilità ≥ 80%)")
print("=" * 100)

certezze_80 = [c for c in certezze_sorted if c['prob'] >= 0.80]

# Escludi Over 0.5 (troppo banale)
certezze_80_filtrate = [c for c in certezze_80 if 'Over 0.5' not in c['mercato']]

# Prendi max 1 evento per partita per diversificare
partite_usate = set()
schedina_super = []

for c in certezze_80_filtrate:
    if c['partita'] not in partite_usate and len(schedina_super) < 6:
        schedina_super.append(c)
        partite_usate.add(c['partita'])

prob_super = 1.0
quota_super = 1.0

for i, c in enumerate(schedina_super, 1):
    prob_super *= c['prob']
    quota_super *= c['quota']

    print(f"\n{i}. {c['partita']}")
    print(f"   🏆 {c['lega']} | ⏰ {c['ora']}")
    print(f"   🎯 {c['mercato']} ({c['categoria']})")
    print(f"   📊 {c['prob']*100:.1f}%")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_super*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_super:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_super*10:.2f}€ | Profitto: {(quota_super-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA EQUILIBRATA (75-80%)
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA EQUILIBRATA (Probabilità 75-85%, Quote migliori)")
print("=" * 100)

certezze_75_85 = [c for c in certezze_sorted if 0.75 <= c['prob'] < 0.85]
certezze_75_85_filtrate = [c for c in certezze_75_85 if 'Over 0.5' not in c['mercato']]

# Ordina per value (prob * quota)
certezze_75_85_value = sorted(certezze_75_85_filtrate,
                               key=lambda x: x['prob'] * x['quota'],
                               reverse=True)

partite_usate2 = set()
schedina_eq = []

for c in certezze_75_85_value:
    if c['partita'] not in partite_usate2 and len(schedina_eq) < 5:
        schedina_eq.append(c)
        partite_usate2.add(c['partita'])

prob_eq = 1.0
quota_eq = 1.0

for i, c in enumerate(schedina_eq, 1):
    prob_eq *= c['prob']
    quota_eq *= c['quota']

    print(f"\n{i}. {c['partita']}")
    print(f"   🏆 {c['lega']} | ⏰ {c['ora']}")
    print(f"   🎯 {c['mercato']} ({c['categoria']})")
    print(f"   📊 {c['prob']*100:.1f}% | Quota {c['quota']:.2f}")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_eq*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_eq:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_eq*10:.2f}€ | Profitto: {(quota_eq-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# RIEPILOGO FINALE
# ========================================
print("\n\n" + "=" * 100)
print("💡 RACCOMANDAZIONI FINALI")
print("=" * 100)

print(f"""
🎯 STATISTICHE:
   • Partite analizzate: {len(partite_uniche)}
   • Certezze trovate (≥75%): {len(certezze_sorted)} eventi
   • Ultra-certezze (≥80%): {len(certezze_80)} eventi
   • Certezze supreme (≥90%): {len([c for c in certezze_sorted if c['prob'] >= 0.90])} eventi

📋 SCHEDINE CONSIGLIATE:

1️⃣ SCHEDINA SUPER SICURA ({len(schedina_super)} eventi, ≥80%)
   → Probabilità: {prob_super*100:.2f}%
   → Quota: {quota_super:.2f}
   → Vincita con 10€: {quota_super*10:.2f}€

2️⃣ SCHEDINA EQUILIBRATA ({len(schedina_eq)} eventi, 75-85%)
   → Probabilità: {prob_eq*100:.2f}%
   → Quota: {quota_eq:.2f}
   → Vincita con 10€: {quota_eq*10:.2f}€

⚠️  NOTA IMPORTANTE:
   Le quote mostrate sono FAIR ODDS matematiche.
   Le quote reali del bookmaker saranno circa 10-15% più basse.

   VERIFICA SEMPRE le quote reali prima di puntare!
""")

db.close()

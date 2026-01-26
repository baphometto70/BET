#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CERTEZZE 17 GENNAIO 2026
Pronostici più vicini alla certezza per OGGI
"""

from database import SessionLocal
from models import Fixture
from datetime import date, datetime
from scipy.stats import poisson

db = SessionLocal()

# OGGI: 17 gennaio 2026
oggi = date(2026, 1, 17)
now = datetime.now()

fixtures = db.query(Fixture).filter(Fixture.date == oggi).all()

print("=" * 100)
print("🎯 CERTEZZE - 17 GENNAIO 2026")
print("=" * 100)
print(f"⏰ Ora corrente: {now.strftime('%H:%M')}")
print(f"📅 Data analisi: {oggi.strftime('%d/%m/%Y')}")
print(f"🔍 Cerco eventi con ALTA PROBABILITÀ (≥70%)")
print("=" * 100)

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
                print(f"⏭️  SKIP: {fix.home} vs {fix.away} ({match_time_str} - già giocata)")
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
    p_under25 = 1 - p_over25
    p_under35 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                    for i in range(4) for j in range(4) if i+j <= 3)

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

    # TUTTI i mercati
    mercati = [
        ('1 (Casa)', p_h, '1X2'),
        ('X (Pareggio)', p_d, '1X2'),
        ('2 (Trasferta)', p_a, '1X2'),
        ('1X', p_1x, 'DOPPIA CHANCE'),
        ('X2', p_x2, 'DOPPIA CHANCE'),
        ('12', p_12, 'DOPPIA CHANCE'),
        ('Over 1.5', p_over15, 'OVER/UNDER'),
        ('Over 2.5', p_over25, 'OVER/UNDER'),
        ('Under 2.5', p_under25, 'OVER/UNDER'),
        ('Under 3.5', p_under35, 'OVER/UNDER'),
        ('GG', p_gg, 'GOL'),
        ('NG', p_ng, 'GOL'),
        ('Multigol 1-3', p_mg_13, 'MULTIGOL'),
        ('Multigol 2-4', p_mg_24, 'MULTIGOL'),
        ('Multigol 2-5', p_mg_25, 'MULTIGOL'),
    ]

    # Solo prob >= 70%, ESCLUDI Over 0.5 (troppo banale)
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
            })

certezze_sorted = sorted(certezze, key=lambda x: x['prob'], reverse=True)

print(f"\n✅ CERTEZZE TROVATE: {len(certezze_sorted)} eventi (probabilità ≥70%)\n")

if not certezze_sorted:
    print("❌ NESSUNA CERTEZZA TROVATA per oggi.")
    print("   Le partite potrebbero essere già finite o non ci sono eventi ≥70%")
    db.close()
    exit()

# ========================================
# ANALISI PER PARTITA
# ========================================
print("=" * 100)
print("📊 ANALISI DETTAGLIATA PER PARTITA")
print("=" * 100)

partite_uniche = list(set([c['partita'] for c in certezze_sorted]))

for partita in partite_uniche:
    certezze_partita = [c for c in certezze_sorted if c['partita'] == partita]
    primo = certezze_partita[0]

    print(f"\n{'─' * 100}")
    print(f"⚽ {primo['partita']}")
    print(f"🏆 {primo['lega']} | ⏰ {primo['ora']}")
    print(f"{'─' * 100}")

    # Raggruppa per categoria
    per_cat = {}
    for c in certezze_partita:
        if c['categoria'] not in per_cat:
            per_cat[c['categoria']] = []
        per_cat[c['categoria']].append(c)

    for cat in ['1X2', 'DOPPIA CHANCE', 'OVER/UNDER', 'GOL', 'MULTIGOL']:
        if cat in per_cat:
            print(f"\n  {cat}:")
            for c in sorted(per_cat[cat], key=lambda x: x['prob'], reverse=True):
                icon = "🔥" if c['prob'] >= 0.85 else "⭐" if c['prob'] >= 0.80 else "✅"
                print(f"    {icon} {c['mercato']:20} {c['prob']*100:5.1f}% (Q ~{c['quota']:.2f})")

# ========================================
# TOP 10 CERTEZZE
# ========================================
print("\n\n" + "=" * 100)
print("🏆 TOP 10 CERTEZZE ASSOLUTE")
print("=" * 100)

for i, c in enumerate(certezze_sorted[:10], 1):
    icon = "🔥" if c['prob'] >= 0.90 else "⭐" if c['prob'] >= 0.85 else "✅"
    print(f"\n{i}. {icon} {c['partita']}")
    print(f"   🏆 {c['lega']} | ⏰ {c['ora']}")
    print(f"   🎯 {c['mercato']} ({c['categoria']}) → {c['prob']*100:.1f}% | Q ~{c['quota']:.2f}")

# ========================================
# SCHEDINA SUPER SICURA
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA CONSIGLIATA: MASSIMA SICUREZZA")
print("=" * 100)

# Prendi max 1 evento per partita, escludi Over 0.5
certezze_filtrate = [c for c in certezze_sorted if 'Over 0.5' not in c['mercato']]

partite_usate = set()
schedina = []

for c in certezze_filtrate:
    if c['partita'] not in partite_usate and len(schedina) < 6:
        schedina.append(c)
        partite_usate.add(c['partita'])

prob_tot = 1.0
quota_tot = 1.0

for i, c in enumerate(schedina, 1):
    prob_tot *= c['prob']
    quota_tot *= c['quota']

    print(f"\n{i}. {c['partita']}")
    print(f"   🏆 {c['lega']} | ⏰ {c['ora']}")
    print(f"   🎯 {c['mercato']} → {c['prob']*100:.1f}%")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot*10:.2f}€ | Profitto: {(quota_tot-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# RIEPILOGO
# ========================================
print("\n\n" + "=" * 100)
print("💡 RIEPILOGO")
print("=" * 100)

print(f"""
📊 STATISTICHE:
   • Partite disponibili oggi: {len(partite_uniche)}
   • Certezze trovate (≥70%): {len(certezze_sorted)}
   • Ultra-certezze (≥80%): {len([c for c in certezze_sorted if c['prob'] >= 0.80])}

📋 SCHEDINA CONSIGLIATA: {len(schedina)} eventi
   → Probabilità: {prob_tot*100:.2f}%
   → Quota fair: {quota_tot:.2f}
   → Vincita con 10€: {quota_tot*10:.2f}€

⚠️  ATTENZIONE:
   Quote FAIR matematiche. Le quote reali del bookmaker saranno 10-15% più basse.
   VERIFICA SEMPRE le quote effettive prima di puntare!
""")

db.close()

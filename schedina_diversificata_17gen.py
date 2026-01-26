#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA DIVERSIFICATA 17 GENNAIO 2026
Eventi VARI con alta probabilità: 1X2, DC, Multigol, GG/NG, Over/Under
"""

from database import SessionLocal
from models import Fixture
from datetime import date, datetime
from scipy.stats import poisson

db = SessionLocal()

oggi = date(2026, 1, 17)
now = datetime.now()

fixtures = db.query(Fixture).filter(Fixture.date == oggi).all()

print("=" * 100)
print("🎯 SCHEDINA DIVERSIFICATA - 17 GENNAIO 2026")
print("=" * 100)
print(f"⏰ Ora: {now.strftime('%H:%M')}")
print(f"🎨 STRATEGIA: Eventi DIVERSI con alta probabilità (≥70%)")
print(f"    Mix: 1X2, Doppia Chance, Multigol, GG/NG, Over/Under")
print("=" * 100)

# Raccogli TUTTE le certezze per categoria
certezze_per_categoria = {
    '1X2': [],
    'DOPPIA CHANCE': [],
    'MULTIGOL': [],
    'GOL': [],
    'OVER/UNDER': []
}

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

    # Lambda
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

    partita_info = {
        'partita': f"{fix.home} vs {fix.away}",
        'lega': fix.league_code,
        'ora': match_time_str,
    }

    # 1X2
    if p_h >= 0.70:
        certezze_per_categoria['1X2'].append({**partita_info, 'mercato': '1 (Casa)', 'prob': p_h, 'quota': 1/p_h})
    if p_d >= 0.70:
        certezze_per_categoria['1X2'].append({**partita_info, 'mercato': 'X (Pareggio)', 'prob': p_d, 'quota': 1/p_d})
    if p_a >= 0.70:
        certezze_per_categoria['1X2'].append({**partita_info, 'mercato': '2 (Trasferta)', 'prob': p_a, 'quota': 1/p_a})

    # Doppia Chance
    if p_1x >= 0.70:
        certezze_per_categoria['DOPPIA CHANCE'].append({**partita_info, 'mercato': '1X', 'prob': p_1x, 'quota': 1/p_1x})
    if p_x2 >= 0.70:
        certezze_per_categoria['DOPPIA CHANCE'].append({**partita_info, 'mercato': 'X2', 'prob': p_x2, 'quota': 1/p_x2})
    if p_12 >= 0.70:
        certezze_per_categoria['DOPPIA CHANCE'].append({**partita_info, 'mercato': '12', 'prob': p_12, 'quota': 1/p_12})

    # Multigol
    if p_mg_13 >= 0.70:
        certezze_per_categoria['MULTIGOL'].append({**partita_info, 'mercato': 'Multigol 1-3', 'prob': p_mg_13, 'quota': 1/p_mg_13})
    if p_mg_24 >= 0.70:
        certezze_per_categoria['MULTIGOL'].append({**partita_info, 'mercato': 'Multigol 2-4', 'prob': p_mg_24, 'quota': 1/p_mg_24})
    if p_mg_25 >= 0.70:
        certezze_per_categoria['MULTIGOL'].append({**partita_info, 'mercato': 'Multigol 2-5', 'prob': p_mg_25, 'quota': 1/p_mg_25})

    # GG/NG
    if p_gg >= 0.70:
        certezze_per_categoria['GOL'].append({**partita_info, 'mercato': 'GG (Goal/Goal)', 'prob': p_gg, 'quota': 1/p_gg})
    if p_ng >= 0.70:
        certezze_per_categoria['GOL'].append({**partita_info, 'mercato': 'NG (No Goal)', 'prob': p_ng, 'quota': 1/p_ng})

    # Over/Under (ESCLUDI Over 1.5 perché troppo comune)
    if p_over25 >= 0.70:
        certezze_per_categoria['OVER/UNDER'].append({**partita_info, 'mercato': 'Over 2.5', 'prob': p_over25, 'quota': 1/p_over25})
    if p_under25 >= 0.70:
        certezze_per_categoria['OVER/UNDER'].append({**partita_info, 'mercato': 'Under 2.5', 'prob': p_under25, 'quota': 1/p_under25})
    if p_under35 >= 0.70:
        certezze_per_categoria['OVER/UNDER'].append({**partita_info, 'mercato': 'Under 3.5', 'prob': p_under35, 'quota': 1/p_under35})

# Ordina per probabilità
for cat in certezze_per_categoria:
    certezze_per_categoria[cat] = sorted(certezze_per_categoria[cat], key=lambda x: x['prob'], reverse=True)

# Mostra statistiche
print("\n📊 CERTEZZE TROVATE PER CATEGORIA:")
for cat, eventi in certezze_per_categoria.items():
    print(f"  • {cat:20} {len(eventi):3} eventi")

# ========================================
# SCHEDINA DIVERSIFICATA
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA CONSIGLIATA: MASSIMA DIVERSIFICAZIONE")
print("=" * 100)
print("Strategia: 1-2 eventi per categoria, massima varietà\n")

schedina = []

# Prendi i migliori 2 per categoria
max_per_categoria = 2
partite_usate = set()

for cat in ['DOPPIA CHANCE', 'MULTIGOL', 'OVER/UNDER', '1X2', 'GOL']:
    count = 0
    for ev in certezze_per_categoria[cat]:
        if ev['partita'] not in partite_usate and count < max_per_categoria:
            schedina.append({**ev, 'categoria': cat})
            partite_usate.add(ev['partita'])
            count += 1

# Ordina per probabilità
schedina = sorted(schedina, key=lambda x: x['prob'], reverse=True)[:8]

prob_tot = 1.0
quota_tot = 1.0

for i, ev in enumerate(schedina, 1):
    prob_tot *= ev['prob']
    quota_tot *= ev['quota']

    print(f"{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']}) → {ev['prob']*100:.1f}%\n")

print(f"{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot*10:.2f}€ | Profitto: {(quota_tot-1)*10:.2f}€")
print(f"🎨 Categorie: {len(set([ev['categoria'] for ev in schedina]))} diverse")
print(f"{'─' * 100}")

# ========================================
# ALTERNATIVE
# ========================================
print("\n\n" + "=" * 100)
print("💡 ALTERNATIVE INTERESSANTI")
print("=" * 100)

# Alt 1: Solo Doppia Chance e Multigol
print("\n🔹 OPZIONE A: Solo DC + Multigol (Quote migliori)")
alt_a = []
partite_a = set()
for ev in certezze_per_categoria['DOPPIA CHANCE'][:3]:
    if ev['partita'] not in partite_a:
        alt_a.append(ev)
        partite_a.add(ev['partita'])
for ev in certezze_per_categoria['MULTIGOL'][:3]:
    if ev['partita'] not in partite_a:
        alt_a.append(ev)
        partite_a.add(ev['partita'])

prob_a = 1.0
quota_a = 1.0
for ev in alt_a[:5]:
    prob_a *= ev['prob']
    quota_a *= ev['quota']
    print(f"  • {ev['partita']} → {ev['mercato']} ({ev['prob']*100:.1f}%)")

print(f"\n  → Prob: {prob_a*100:.1f}% | Quota: {quota_a:.2f} | Con 10€: {quota_a*10:.2f}€")

# Alt 2: Solo Over/Under e Multigol
print("\n🔹 OPZIONE B: Solo O/U + Multigol")
alt_b = []
for ev in certezze_per_categoria['OVER/UNDER'][:3]:
    alt_b.append(ev)
for ev in certezze_per_categoria['MULTIGOL'][:3]:
    if ev['partita'] not in [e['partita'] for e in alt_b]:
        alt_b.append(ev)

prob_b = 1.0
quota_b = 1.0
for ev in alt_b[:6]:
    prob_b *= ev['prob']
    quota_b *= ev['quota']
    print(f"  • {ev['partita']} → {ev['mercato']} ({ev['prob']*100:.1f}%)")

print(f"\n  → Prob: {prob_b*100:.1f}% | Quota: {quota_b:.2f} | Con 10€: {quota_b*10:.2f}€")

print("\n" + "=" * 100)
print("⚠️  RICORDA: Quote FAIR matematiche, bookmaker sarà 10-15% più basso!")
print("=" * 100)

db.close()

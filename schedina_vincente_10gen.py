#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEDINA VINCENTE 10 GENNAIO 2026
Eventi diversificati con ALTA PROBABILITÀ e ALTA VINCITA
Mix intelligente di 1X2, Doppia Chance, GG/NG, Multigol
"""

from database import SessionLocal
from models import Fixture
from datetime import date, datetime
from scipy.stats import poisson

db = SessionLocal()

# Query per tutte le partite del 10 gennaio 2026
fixtures = db.query(Fixture).filter(Fixture.date == date(2026, 1, 10)).all()

# ORA CORRENTE per filtrare partite già giocate
now = datetime.now()
current_time = now.time()
print(f"\n⏰ Ora corrente: {current_time.strftime('%H:%M')}")
print(f"📅 Data: {now.strftime('%Y-%m-%d')}\n")

print("=" * 100)
print("🎯 SCHEDINA VINCENTE 10 GENNAIO 2026")
print("=" * 100)
print("STRATEGIA: Alta probabilità (≥65%) + Quote interessanti (≥1.35)")
print("DIVERSIFICAZIONE: 1X2, Doppia Chance, GG/NG, Multigol, Over/Under")
print("=" * 100)

# Calcola tutte le probabilità per ogni partita
eventi_interessanti = []

for fix in fixtures:
    if not fix.feature:
        continue

    feat = fix.feature
    if not all([feat.xg_for_home, feat.xg_against_home, feat.xg_for_away, feat.xg_against_away]):
        continue

    # SALTA partite già giocate o in corso
    match_time_str = fix.time_local or fix.time
    if match_time_str:
        try:
            match_time = datetime.strptime(match_time_str, "%H:%M").time()
            # Se la partita è iniziata più di 2 ore fa, probabilmente è finita
            match_datetime = datetime.combine(fix.date, match_time)
            if match_datetime < now:
                print(f"⏭️  SKIP: {fix.home} vs {fix.away} (ore {match_time_str} - già giocata)")
                continue
        except:
            pass  # Se non riesco a parsare l'orario, includi la partita

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
    p_over15 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(2) for j in range(2) if i+j <= 1)
    p_over25 = 1 - sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                       for i in range(3) for j in range(3) if i+j <= 2)

    # Goal/No Goal
    p_gg = 1 - (poisson.pmf(0, lam_h) * sum(poisson.pmf(j, lam_a) for j in range(10)) +
                sum(poisson.pmf(i, lam_h) for i in range(10)) * poisson.pmf(0, lam_a) -
                poisson.pmf(0, lam_h) * poisson.pmf(0, lam_a))
    p_ng = 1 - p_gg

    # Multigol
    p_mg_13 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 1 <= i+j <= 3)
    p_mg_25 = sum(poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
                  for i in range(10) for j in range(10) if 2 <= i+j <= 5)

    # CRITERIO INTELLIGENTE: prob >= 65% E quota >= 1.35 (escludi Over 0.5 e 12 che pagano troppo poco)
    candidati = [
        ('1 (Vittoria Casa)', p_h, 'RISULTATO ESATTO'),
        ('X (Pareggio)', p_d, 'RISULTATO ESATTO'),
        ('2 (Vittoria Trasferta)', p_a, 'RISULTATO ESATTO'),
        ('1X (Casa o Pareggio)', p_1x, 'DOPPIA CHANCE'),
        ('X2 (Pareggio o Trasferta)', p_x2, 'DOPPIA CHANCE'),
        ('Over 1.5', p_over15, 'OVER/UNDER'),
        ('Over 2.5', p_over25, 'OVER/UNDER'),
        ('GG (Goal/Goal)', p_gg, 'GOL'),
        ('NG (No Goal)', p_ng, 'GOL'),
        ('Multigol 1-3', p_mg_13, 'MULTIGOL'),
        ('Multigol 2-5', p_mg_25, 'MULTIGOL'),
    ]

    for mercato, prob, categoria in candidati:
        quota = 1 / prob

        # CRITERI:
        # 1. Probabilità >= 65% (alta sicurezza)
        # 2. Quota >= 1.35 (vincita decente, escludi 12 e Over 0.5)
        # 3. Quota <= 2.00 (non troppo rischiosa)
        if prob >= 0.65 and 1.35 <= quota <= 2.00:
            eventi_interessanti.append({
                'partita': f"{fix.home} vs {fix.away}",
                'lega': fix.league_code,
                'ora': fix.time_local or fix.time,
                'mercato': mercato,
                'categoria': categoria,
                'prob': prob,
                'quota': quota,
                'value_score': prob * quota,  # Score combinato prob*quota
            })

# Ordina per value_score (migliore rapporto prob/quota)
eventi_sorted = sorted(eventi_interessanti, key=lambda x: x['value_score'], reverse=True)

print(f"\n✅ Eventi trovati: {len(eventi_sorted)}")
print(f"   Criteri: Probabilità ≥65%, Quota tra 1.35 e 2.00\n")

# ========================================
# SCHEDINA #1: TOP 5 EVENTI VALUE
# ========================================
print("=" * 100)
print("📋 SCHEDINA #1: TOP 5 EVENTI MIGLIORE VALUE (Prob × Quota)")
print("=" * 100)

schedina_1 = eventi_sorted[:5]
prob_tot_1 = 1.0
quota_tot_1 = 1.0

categorie_usate = set()
for i, ev in enumerate(schedina_1, 1):
    prob_tot_1 *= ev['prob']
    quota_tot_1 *= ev['quota']
    categorie_usate.add(ev['categoria'])

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']})")
    print(f"   📊 Probabilità: {ev['prob']*100:.1f}% | Quota: {ev['quota']:.2f} | Value: {ev['value_score']:.3f}")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_1*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot_1:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot_1*10:.2f}€ | Profitto: {(quota_tot_1-1)*10:.2f}€")
print(f"🎨 Diversificazione: {len(categorie_usate)} categorie diverse ({', '.join(categorie_usate)})")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #2: 7 EVENTI MASSIMA DIVERSIFICAZIONE
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #2: 7 EVENTI DIVERSIFICATI (Mix tutte le categorie)")
print("=" * 100)

# Seleziona al massimo 2 eventi per categoria
categorie_count = {}
schedina_2 = []

for ev in eventi_sorted:
    cat = ev['categoria']
    if categorie_count.get(cat, 0) < 2 and len(schedina_2) < 7:
        schedina_2.append(ev)
        categorie_count[cat] = categorie_count.get(cat, 0) + 1

prob_tot_2 = 1.0
quota_tot_2 = 1.0

for i, ev in enumerate(schedina_2, 1):
    prob_tot_2 *= ev['prob']
    quota_tot_2 *= ev['quota']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']})")
    print(f"   📊 Probabilità: {ev['prob']*100:.1f}% | Quota: {ev['quota']:.2f}")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_2*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot_2:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot_2*10:.2f}€ | Profitto: {(quota_tot_2-1)*10:.2f}€")
print(f"🎨 Diversificazione: {len(categorie_count)} categorie ({dict(categorie_count)})")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #3: SOLO PROB >= 70% (Ultra Sicura)
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #3: ULTRA SICURA (Solo probabilità ≥70%)")
print("=" * 100)

schedina_3 = [ev for ev in eventi_sorted if ev['prob'] >= 0.70][:6]
prob_tot_3 = 1.0
quota_tot_3 = 1.0

for i, ev in enumerate(schedina_3, 1):
    prob_tot_3 *= ev['prob']
    quota_tot_3 *= ev['quota']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']})")
    print(f"   📊 Probabilità: {ev['prob']*100:.1f}% | Quota: {ev['quota']:.2f}")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_3*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot_3:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot_3*10:.2f}€ | Profitto: {(quota_tot_3-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #4: QUOTA ALTA (Massimo guadagno)
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #4: QUOTA ALTA (Massimo profitto, prob ≥68%)")
print("=" * 100)

# Ordina per quota ma mantieni prob >= 68%
schedina_4_candidati = [ev for ev in eventi_sorted if ev['prob'] >= 0.68]
schedina_4 = sorted(schedina_4_candidati, key=lambda x: x['quota'], reverse=True)[:5]

prob_tot_4 = 1.0
quota_tot_4 = 1.0

for i, ev in enumerate(schedina_4, 1):
    prob_tot_4 *= ev['prob']
    quota_tot_4 *= ev['quota']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']})")
    print(f"   📊 Probabilità: {ev['prob']*100:.1f}% | Quota: {ev['quota']:.2f}")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_4*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot_4:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot_4*10:.2f}€ | Profitto: {(quota_tot_4-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# SCHEDINA #5: SOLO GOL (GG/NG + Multigol)
# ========================================
print("\n\n" + "=" * 100)
print("📋 SCHEDINA #5: SPECIALISTA GOL (GG/NG + Multigol)")
print("=" * 100)

schedina_5 = [ev for ev in eventi_sorted if ev['categoria'] in ['GOL', 'MULTIGOL']][:6]
prob_tot_5 = 1.0
quota_tot_5 = 1.0

for i, ev in enumerate(schedina_5, 1):
    prob_tot_5 *= ev['prob']
    quota_tot_5 *= ev['quota']

    print(f"\n{i}. {ev['partita']}")
    print(f"   🏆 {ev['lega']} | ⏰ {ev['ora']}")
    print(f"   🎯 {ev['mercato']} ({ev['categoria']})")
    print(f"   📊 Probabilità: {ev['prob']*100:.1f}% | Quota: {ev['quota']:.2f}")

print(f"\n{'─' * 100}")
print(f"📊 PROBABILITÀ COMBINATA: {prob_tot_5*100:.2f}%")
print(f"💰 QUOTA TOTALE: {quota_tot_5:.2f}")
print(f"💵 Con 10€ → Vincita: {quota_tot_5*10:.2f}€ | Profitto: {(quota_tot_5-1)*10:.2f}€")
print(f"{'─' * 100}")

# ========================================
# RIEPILOGO FINALE
# ========================================
print("\n\n" + "=" * 100)
print("📊 RIEPILOGO SCHEDINE")
print("=" * 100)

schedine_riepilogo = [
    ("🥇 SCHEDINA #1: Top 5 Value", len(schedina_1), prob_tot_1, quota_tot_1),
    ("🎨 SCHEDINA #2: 7 Diversificati", len(schedina_2), prob_tot_2, quota_tot_2),
    ("🛡️  SCHEDINA #3: Ultra Sicura (≥70%)", len(schedina_3), prob_tot_3, quota_tot_3),
    ("💰 SCHEDINA #4: Quota Alta", len(schedina_4), prob_tot_4, quota_tot_4),
    ("⚽ SCHEDINA #5: Specialista Gol", len(schedina_5), prob_tot_5, quota_tot_5),
]

for nome, num_eventi, prob, quota in schedine_riepilogo:
    vincita_10 = quota * 10
    profitto_10 = (quota - 1) * 10
    print(f"\n{nome}")
    print(f"  📌 {num_eventi} eventi | Prob: {prob*100:.2f}% | Quota: {quota:.2f}")
    print(f"  💵 Con 10€ → Vincita: {vincita_10:.2f}€ | Profitto: {profitto_10:.2f}€")

print("\n" + "=" * 100)
print("💡 CONSIGLI:")
print("=" * 100)
print("""
🥇 SCHEDINA #1 (Top 5 Value): CONSIGLIATA per chi cerca il miglior equilibrio
   • Migliore rapporto probabilità/quota
   • Eventi selezionati matematicamente

🛡️  SCHEDINA #3 (Ultra Sicura): Per chi vuole massima affidabilità
   • Solo eventi con prob ≥70%
   • Quota più bassa ma rischio minimo

💰 SCHEDINA #4 (Quota Alta): Per chi vuole vincere di più
   • Quote più alte mantenendo buona probabilità (≥68%)
   • Rischio leggermente maggiore ma profitto massimo

🎨 SCHEDINA #2 (Diversificata): Per ridurre correlazione tra eventi
   • Mix di tutte le categorie
   • Eventi più indipendenti tra loro

⚠️  NOTA IMPORTANTE:
   Queste sono quote FAIR calcolate matematicamente.
   Le quote reali del bookmaker saranno più basse (margine ~10-15%).

   Esempio: Quota Fair 1.50 → Quota Bookmaker ~1.35-1.40

   VERIFICA SEMPRE le quote effettive del tuo bookmaker prima di puntare!
""")

db.close()

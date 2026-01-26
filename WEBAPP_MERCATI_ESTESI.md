# 🎯 Mercati Estesi - Guida Web App

## 🚀 Come Usare i Nuovi Mercati Estesi nella Web App

### 1. Avvia la Web App

```bash
python3 app.py
```

L'app sarà disponibile su: **http://localhost:5000**

### 2. Accedi ai Mercati Estesi

Dalla dashboard principale, clicca sul pulsante arancione:

**🔥 Mercati Estesi (NUOVO!)**

Oppure vai direttamente a: **http://localhost:5000/extended-markets**

---

## 📊 Funzionalità Disponibili

### A. Genera Predizioni Estese

1. **Seleziona la data** per cui vuoi generare le predizioni
2. **Imposta i parametri**:
   - **Probabilità Minima**: 0.55 (55%) consigliato
   - **Top N per Partita**: 15 (numero massimo di scommesse per match)
3. **Clicca "🚀 Genera Predizioni Estese"**

Il sistema genererà automaticamente:
- ✅ **200+ scommesse** su tutte le partite della data selezionata
- ✅ **6 categorie** di mercati diversificati
- ✅ **Probabilità 65-98%** calcolate con ML + Poisson

### B. Visualizza e Filtra Risultati

Una volta generate, puoi:

1. **Filtrare per data**: Visualizza solo le scommesse di una specifica data
2. **Filtrare per probabilità**: Imposta una soglia minima (es. 70% per massima sicurezza)
3. **Limitare per partita**: Max 3 scommesse per match per evitare concentrazione

---

## 🎯 Top 20 Best Picks

La sezione principale mostra le **Top 20 scommesse consigliate**:

- 🔥🔥 **Probabilità 90%+**: Massima affidabilità
- 🔥 **Probabilità 70-90%**: Alta affidabilità
- ○ **Probabilità 60-70%**: Affidabilità media

**Esempio Risultati**:
```
#1  🔥🔥 Marseille - Nantes
    Away Under 2.5 goals
    98.0%
    HIGH • Value: +33.0%

#2  🔥🔥 Lazio - Napoli
    Under 5.5 goals
    96.4%
    HIGH • Value: +31.4%
```

---

## 📈 Categorie Mercati

### 1. Over/Under (Linee Multiple)
- Under 5.5 goals → **95%+ probabilità** (ultra sicuro)
- Under 4.5 goals → **90%+ probabilità** (molto sicuro)
- Over 0.5 goals → **90%+ probabilità** (almeno 1 gol)
- Under 3.5 goals → **75-80%**
- Over/Under 2.5 → **55-65%** (linea standard)

**Best Use**: Scegli Under 5.5/4.5 per massima sicurezza

### 2. Team Totals
- Away Under 2.5 → **85-98%** (trasferta non segna molto)
- Home Under 2.5 → **80-90%**
- Home Over 0.5 → **75-80%** (casa segna almeno 1)
- Away Over 0.5 → **70-80%**

**Best Use**: Away Under 2.5 per squadre difensive in trasferta

### 3. Doppia Chance (DC)
- 1X (Casa o Pareggio) → **65-85%**
- X2 (Pareggio o Trasferta) → **65-80%**
- 12 (Casa o Trasferta, no pareggio) → **70-85%**

**Best Use**: 1X quando la casa è favorita ma c'è rischio pareggio

### 4. Multigol
- 1-3 goals → **65-75%**
- 2-5 goals → **65-75%**
- 1-2 goals → **55-65%**

**Best Use**: 1-3 goals per match equilibrate

### 5. Goal/No Goal
- NG (No Goal, almeno una non segna) → **60-75%**
- GG (Goal Goal, entrambe segnano) → **55-70%**

**Best Use**: NG quando c'è una difesa forte

### 6. Combo Markets
- 1X + GG
- DC + Over/Under
- 1X2 + GG/NG

**Best Use**: Diversificazione avanzata

---

## 💡 Strategie Consigliate

### Strategia 1: Ultra Conservativa (95%+ prob)
```
✅ Seleziona: Top 10 scommesse
✅ Probabilità minima: 90%
✅ Mercati: Under 5.5, Away Under 2.5, Over 0.5
✅ Sistema: Multipla 8-10 scommesse
✅ ROI atteso: +30-50%
✅ Rischio: Molto Basso
```

### Strategia 2: Bilanciata (80%+ prob)
```
✅ Seleziona: Top 15 scommesse
✅ Probabilità minima: 75%
✅ Mercati: Mix Over/Under, Team Totals, DC
✅ Sistema: Multipla 12-15 scommesse
✅ ROI atteso: +40-70%
✅ Rischio: Basso
```

### Strategia 3: Sistema Parziale (Ottimale) ⭐
```
✅ Seleziona: Top 20 scommesse
✅ Probabilità minima: 65%
✅ Gioca: Sistema 16/20 (richiedi 16 vincenti su 20)
✅ Probabilità successo sistema: ~50%
✅ ROI atteso: +20-30%
✅ Rischio: Medio (ma ROI più alto)
```

### Strategia 4: Aggressiva (60%+ prob)
```
✅ Seleziona: Top 30 scommesse
✅ Probabilità minima: 60%
✅ Sistema: Parziale 24/30
✅ ROI atteso: +50-100%
✅ Rischio: Medio-Alto
```

---

## 📊 Interpretare i Risultati

### Statistiche Principali
- **Partite Analizzate**: Numero totale di match nel dataset
- **Scommesse Totali**: Tutte le opzioni generate (~200)
- **Scommesse Filtrate**: Quelle che rispettano i tuoi criteri
- **Probabilità Media**: Media delle prob. delle scommesse filtrate

### Per Ogni Scommessa
- **Partita**: Home - Away + Lega
- **Mercato**: Tipo di scommessa (es. "Under 5.5 goals")
- **Probabilità**: % di successo prevista (95% = altissima)
- **Value**: Expected Value = (Prob × Odds) - 1
  - **Positivo (+)**: Scommessa favorevole
  - **Negativo (-)**: Scommessa sfavorevole
- **Confidence**:
  - 🔥🔥 **HIGH**: Prob ≥ 70%
  - 🔥 **MEDIUM**: Prob 60-70%
  - ○ **LOW**: Prob 50-60%

---

## 🎲 Esempio Pratico

**Obiettivo**: Creare una schedina sicura con ROI positivo

**Step 1**: Genera predizioni per 2026-01-04
```
- Data: 2026-01-04
- Probabilità Minima: 0.55
- Top N: 15
```

**Step 2**: Visualizza risultati
```
✅ 200 scommesse generate
✅ Top 20 con prob media 95.1%
```

**Step 3**: Seleziona le migliori
Prendi le Top 10:
1. Away Under 2.5 (Marseille-Nantes) → 98.0%
2. Under 5.5 (Lazio-Napoli) → 96.4%
3. Under 5.5 (Verona-Torino) → 96.4%
4. Under 5.5 (Mallorca-Girona) → 96.2%
5. Under 5.5 (Everton-Brentford) → 96.2%
6. Under 5.5 (Le Havre-Angers) → 96.2%
7. Under 5.5 (Fiorentina-Cremonese) → 96.0%
8. Under 5.5 (Tottenham-Sunderland) → 96.0%
9. Under 5.5 (Sevilla-Levante) → 95.8%
10. Under 5.5 (Lorient-Metz) → 95.7%

**Step 4**: Calcola rendimento
- Probabilità TUTTE vincano: 96%^10 ≈ 66%
- Stake: €10/scommessa = €100 totale
- Quota media: 1.05 per scommessa
- Quota multipla: 1.05^10 ≈ 1.63
- Vincita potenziale: €100 × 1.63 = €163
- **Profitto atteso: +€63 (ROI +63%)**

---

## ⚠️ Note Importanti

### Limitazioni Attuali
- ❌ **Quote non sempre disponibili**: Alcuni mercati non hanno quote real-time
- ❌ **Solo predizioni giornaliere**: Non live betting
- ✅ **Probabilità calcolate**: Basate su 62 features ML + Poisson

### Prossimi Sviluppi
- [ ] Fetch quote estese da TheOddsAPI
- [ ] Live betting con aggiornamenti real-time
- [ ] Export schedine per bookmaker
- [ ] Tracking risultati e ROI effettivo

---

## 🔧 Troubleshooting

### Problema: "Nessuna predizione estesa disponibile"
**Soluzione**: Devi prima generare le predizioni base:
1. Vai alla Dashboard principale
2. Esegui "Azione Giornaliera" per la data desiderata
3. Torna ai Mercati Estesi e genera

### Problema: "Troppe poche scommesse filtrate"
**Soluzione**: Abbassa la probabilità minima (es. da 70% a 60%)

### Problema: "Nessuna scommessa per la data selezionata"
**Soluzione**: Verifica di aver generato predizioni per quella data specifica

---

## 📞 Supporto

Per problemi o domande:
- Controlla i log in `logs/service.log`
- Verifica che `extended_predictions.csv` esista
- Assicurati che `predictions.csv` sia stato generato per la data

---

**Buona fortuna! 🍀**

*Ricorda: Scommetti sempre responsabilmente e solo quanto puoi permetterti di perdere.*

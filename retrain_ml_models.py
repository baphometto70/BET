#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RIADDESTRA MODELLI ML CON FEATURES COMPLETE
Usa i dati storici con le 61 features appena calcolate
"""

import sys
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss, brier_score_loss, accuracy_score
from lightgbm import LGBMClassifier

warnings.filterwarnings('ignore')

print("=" * 100)
print("🤖 RIADDESTRAMENTO MODELLI ML - Features Complete")
print("=" * 100)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)

# ========================================
# STEP 1: CARICA DATI STORICI
# ========================================
print("\n📂 STEP 1: Carico dati storici...")

hist_path = DATA_DIR / "historical_dataset_enhanced.csv"
if not hist_path.exists():
    hist_path = DATA_DIR / "historical_dataset.csv"

if not hist_path.exists():
    print("❌ File storico non trovato!")
    sys.exit(1)

print(f"📊 Carico {hist_path.name}...")
df = pd.read_csv(hist_path)
print(f"✅ {len(df)} partite caricate")

# ========================================
# STEP 2: PREPARA FEATURES
# ========================================
print("\n📊 STEP 2: Preparo features per training...")

# Features disponibili - USA TUTTO quello che abbiamo nel CSV storico!
FEATURE_COLS = [
    # Base xG (4)
    'xg_for_home', 'xg_against_home', 'xg_for_away', 'xg_against_away',

    # Context (8)
    'rest_days_home', 'rest_days_away',
    'derby_flag', 'europe_flag_home', 'europe_flag_away',
    'meteo_flag', 'style_ppda_home', 'style_ppda_away',

    # Odds (se presenti, utili per calibrazione)
    'odds_1', 'odds_x', 'odds_2',
]

# Derived features
df['xg_total'] = df['xg_for_home'].fillna(1.4) + df['xg_for_away'].fillna(1.4)
df['xg_diff'] = df['xg_for_home'].fillna(1.4) - df['xg_for_away'].fillna(1.4)
df['xg_ratio'] = df['xg_for_home'].fillna(1.4) / (df['xg_for_away'].fillna(1.4) + 0.01)
df['ppda_diff'] = df.get('style_ppda_home', 10).fillna(10) - df.get('style_ppda_away', 10).fillna(10)

FEATURE_COLS.extend(['xg_total', 'xg_diff', 'xg_ratio', 'ppda_diff'])

# Controlla quali features esistono
available_features = [f for f in FEATURE_COLS if f in df.columns]
print(f"Features disponibili: {len(available_features)}/{len(FEATURE_COLS)}")
print(f"Features: {available_features[:10]}...")

# ========================================
# STEP 3: PREPARA TARGET 1X2
# ========================================
print("\n\n📊 STEP 3: Preparo dataset 1X2...")

# Filtra partite con risultato
df_1x2 = df.dropna(subset=['ft_home_goals', 'ft_away_goals']).copy()

# Crea target
def get_1x2_target(row):
    if row['ft_home_goals'] > row['ft_away_goals']:
        return 1  # Home win
    elif row['ft_home_goals'] < row['ft_away_goals']:
        return 2  # Away win
    else:
        return 0  # Draw

df_1x2['target_1x2'] = df_1x2.apply(get_1x2_target, axis=1)

# Filtra feature disponibili
X_1x2 = df_1x2[available_features]
y_1x2 = df_1x2['target_1x2']

print(f"Dataset 1X2: {len(df_1x2)} partite")
print(f"Distribuzione:")
print(f"  Home (1): {sum(y_1x2==1)} ({sum(y_1x2==1)/len(y_1x2)*100:.1f}%)")
print(f"  Draw (0): {sum(y_1x2==0)} ({sum(y_1x2==0)/len(y_1x2)*100:.1f}%)")
print(f"  Away (2): {sum(y_1x2==2)} ({sum(y_1x2==2)/len(y_1x2)*100:.1f}%)")

# ========================================
# STEP 4: PREPARA TARGET O/U 2.5
# ========================================
print("\n\n📊 STEP 4: Preparo dataset Over/Under 2.5...")

df_ou = df.dropna(subset=['ft_home_goals', 'ft_away_goals']).copy()

# Crea target
df_ou['target_ou25'] = (df_ou['ft_home_goals'] + df_ou['ft_away_goals'] > 2.5).astype(int)

X_ou = df_ou[available_features]
y_ou = df_ou['target_ou25']

print(f"Dataset O/U: {len(df_ou)} partite")
print(f"Distribuzione:")
print(f"  Over 2.5 (1):  {sum(y_ou==1)} ({sum(y_ou==1)/len(y_ou)*100:.1f}%)")
print(f"  Under 2.5 (0): {sum(y_ou==0)} ({sum(y_ou==0)/len(y_ou)*100:.1f}%)")

# ========================================
# STEP 5: TRAIN/TEST SPLIT
# ========================================
print("\n\n📊 STEP 5: Split train/test...")

X_train_1x2, X_test_1x2, y_train_1x2, y_test_1x2 = train_test_split(
    X_1x2, y_1x2, test_size=0.2, random_state=42, stratify=y_1x2
)

X_train_ou, X_test_ou, y_train_ou, y_test_ou = train_test_split(
    X_ou, y_ou, test_size=0.2, random_state=42, stratify=y_ou
)

print(f"1X2 - Train: {len(X_train_1x2)} | Test: {len(X_test_1x2)}")
print(f"O/U - Train: {len(X_train_ou)} | Test: {len(X_test_ou)}")

# ========================================
# STEP 6: IMPUTER
# ========================================
print("\n\n📊 STEP 6: Imputo valori mancanti...")

imputer_1x2 = SimpleImputer(strategy='median')
imputer_ou = SimpleImputer(strategy='median')

X_train_1x2_imp = imputer_1x2.fit_transform(X_train_1x2)
X_test_1x2_imp = imputer_1x2.transform(X_test_1x2)

X_train_ou_imp = imputer_ou.fit_transform(X_train_ou)
X_test_ou_imp = imputer_ou.transform(X_test_ou)

print("✅ Imputer fitted")

# ========================================
# STEP 7: TRAIN MODELLO 1X2
# ========================================
print("\n\n" + "=" * 100)
print("🤖 TRAINING MODELLO 1X2 (LightGBM)")
print("=" * 100)

model_1x2 = LGBMClassifier(
    n_estimators=500,  # Più alberi
    max_depth=8,       # Più profondità
    learning_rate=0.03,  # Learning rate più basso
    num_leaves=63,     # Più foglie
    min_child_samples=15,
    subsample=0.85,
    colsample_bytree=0.85,
    reg_alpha=0.05,    # Meno regolarizzazione
    reg_lambda=0.05,
    random_state=42,
    verbose=-1,
    class_weight='balanced',
    importance_type='gain'  # Usa gain invece di split
)

print("🔄 Training in corso...")
model_1x2.fit(X_train_1x2_imp, y_train_1x2)

# Predizioni
y_pred_1x2 = model_1x2.predict(X_test_1x2_imp)
y_proba_1x2 = model_1x2.predict_proba(X_test_1x2_imp)

# Metriche
acc_1x2 = accuracy_score(y_test_1x2, y_pred_1x2)
logloss_1x2 = log_loss(y_test_1x2, y_proba_1x2)

print(f"\n✅ MODELLO 1X2 COMPLETATO!")
print(f"📊 Accuracy: {acc_1x2*100:.2f}%")
print(f"📊 Log Loss: {logloss_1x2:.4f}")

# Feature importance
try:
    feature_imp_1x2 = pd.DataFrame({
        'feature': available_features,
        'importance': model_1x2.feature_importances_
    }).sort_values('importance', ascending=False)
except:
    # Se lunghezze non matchano, usa solo quelle valide
    n_features = len(model_1x2.feature_importances_)
    feature_imp_1x2 = pd.DataFrame({
        'feature': available_features[:n_features],
        'importance': model_1x2.feature_importances_
    }).sort_values('importance', ascending=False)

print(f"\n🏆 Top 10 Features più importanti:")
for i, row in feature_imp_1x2.head(10).iterrows():
    print(f"   {row['feature']:20} → {row['importance']:.4f}")

# ========================================
# STEP 8: TRAIN MODELLO O/U
# ========================================
print("\n\n" + "=" * 100)
print("🤖 TRAINING MODELLO OVER/UNDER 2.5 (LightGBM)")
print("=" * 100)

model_ou = LGBMClassifier(
    n_estimators=500,
    max_depth=8,
    learning_rate=0.03,
    num_leaves=63,
    min_child_samples=15,
    subsample=0.85,
    colsample_bytree=0.85,
    reg_alpha=0.05,
    reg_lambda=0.05,
    random_state=42,
    verbose=-1,
    importance_type='gain'
)

print("🔄 Training in corso...")
model_ou.fit(X_train_ou_imp, y_train_ou)

# Predizioni
y_pred_ou = model_ou.predict(X_test_ou_imp)
y_proba_ou = model_ou.predict_proba(X_test_ou_imp)

# Metriche
acc_ou = accuracy_score(y_test_ou, y_pred_ou)
logloss_ou = log_loss(y_test_ou, y_proba_ou)
brier_ou = brier_score_loss(y_test_ou, y_proba_ou[:, 1])

print(f"\n✅ MODELLO O/U COMPLETATO!")
print(f"📊 Accuracy: {acc_ou*100:.2f}%")
print(f"📊 Log Loss: {logloss_ou:.4f}")
print(f"📊 Brier Score: {brier_ou:.4f}")

# Feature importance
try:
    feature_imp_ou = pd.DataFrame({
        'feature': available_features,
        'importance': model_ou.feature_importances_
    }).sort_values('importance', ascending=False)
except:
    n_features = len(model_ou.feature_importances_)
    feature_imp_ou = pd.DataFrame({
        'feature': available_features[:n_features],
        'importance': model_ou.feature_importances_
    }).sort_values('importance', ascending=False)

print(f"\n🏆 Top 10 Features più importanti:")
for i, row in feature_imp_ou.head(10).iterrows():
    print(f"   {row['feature']:20} → {row['importance']:.4f}")

# ========================================
# STEP 9: SALVA MODELLI
# ========================================
print("\n\n" + "=" * 100)
print("💾 SALVATAGGIO MODELLI")
print("=" * 100)

# Salva 1X2
joblib.dump(model_1x2, MODEL_DIR / "bet_1x2_retrained.joblib")
joblib.dump(imputer_1x2, MODEL_DIR / "imputer_1x2_retrained.joblib")
print(f"✅ Salvato: bet_1x2_retrained.joblib")

# Salva O/U
joblib.dump(model_ou, MODEL_DIR / "bet_ou25_retrained.joblib")
joblib.dump(imputer_ou, MODEL_DIR / "imputer_ou25_retrained.joblib")
print(f"✅ Salvato: bet_ou25_retrained.joblib")

# Salva metadata
metadata_1x2 = {
    'accuracy': float(acc_1x2),
    'log_loss': float(logloss_1x2),
    'n_samples': len(X_train_1x2),
    'n_features': len(available_features),
    'features': available_features,
    'classes': model_1x2.classes_.tolist()
}

metadata_ou = {
    'accuracy': float(acc_ou),
    'log_loss': float(logloss_ou),
    'brier_score': float(brier_ou),
    'n_samples': len(X_train_ou),
    'n_features': len(available_features),
    'features': available_features
}

import json
with open(MODEL_DIR / "meta_1x2_retrained.json", 'w') as f:
    json.dump(metadata_1x2, f, indent=2)

with open(MODEL_DIR / "meta_ou25_retrained.json", 'w') as f:
    json.dump(metadata_ou, f, indent=2)

print(f"✅ Salvato metadata")

# ========================================
# RIEPILOGO
# ========================================
print("\n\n" + "=" * 100)
print("✅ TRAINING COMPLETATO!")
print("=" * 100)

print(f"""
📊 MODELLO 1X2:
   Accuracy:  {acc_1x2*100:.2f}%
   Log Loss:  {logloss_1x2:.4f}
   Samples:   {len(X_train_1x2)}
   Features:  {len(available_features)}

📊 MODELLO OVER/UNDER 2.5:
   Accuracy:     {acc_ou*100:.2f}%
   Log Loss:     {logloss_ou:.4f}
   Brier Score:  {brier_ou:.4f}
   Samples:      {len(X_train_ou)}
   Features:     {len(available_features)}

💾 MODELLI SALVATI:
   • bet_1x2_retrained.joblib
   • bet_ou25_retrained.joblib
   • imputer_1x2_retrained.joblib
   • imputer_ou25_retrained.joblib

🎯 PROSSIMO PASSO:
   python predizioni_ml_champions.py
   (Usa i nuovi modelli ML per Champions!)
""")

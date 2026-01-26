#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parent
CFG_PATH = ROOT / "config.toml"


def get_db_url() -> str:
    """
    Costruisce l'URL di connessione al database leggendo da config.toml.
    Se manca config/credenziali o se USE_SQLITE=1, fa fallback a SQLite locale.
    """
    # Forza SQLite via env
    if os.getenv("USE_SQLITE") == "1":
        return f"sqlite:///{(ROOT / 'data' / 'bet.db')}"

    if not CFG_PATH.exists():
        # Fallback silenzioso a SQLite se manca config
        return f"sqlite:///{(ROOT / 'data' / 'bet.db')}"

    cfg = tomllib.loads(CFG_PATH.read_text(encoding="utf-8"))
    db_cfg = cfg.get("database", {})

    user = db_cfg.get("user") or os.getenv("DB_USER")
    password = db_cfg.get("password") or os.getenv("DB_PASSWORD")
    host = db_cfg.get("host", "localhost")
    port = db_cfg.get("port", 5432)
    dbname = db_cfg.get("dbname", "bet_db")

    if not user or not password:
        # Fallback a SQLite se credenziali assenti
        return f"sqlite:///{(ROOT / 'data' / 'bet.db')}"

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


DATABASE_URL = f"sqlite:///{os.path.expanduser('~/Develop/BET/BET/bet.db')}"

# Aggiunto pool_pre_ping=True per gestire connessioni "stantie".
# SQLAlchemy verificherà la connessione prima di usarla, prevenendo errori
# comuni con pool di connessioni di lunga durata.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
init_db.py
----------
Script una-tantum per creare le tabelle nel database PostgreSQL.
Legge la configurazione da `config.toml` e usa i modelli definiti in `models.py`.

Esegui questo script solo una volta per preparare il database.
"""

from sqlalchemy.exc import OperationalError
from database import Base, engine


def main():
    print("Inizializzazione del database...")

    # 1. Verifica connessione
    try:
        print("Tentativo di connessione al database...")
        connection = engine.connect()
        connection.close()
        print("✅ Connessione al database riuscita.")
    except OperationalError as e:
        print("\n❌ ERRORE: Impossibile connettersi al database.")
        print("Verifica che PostgreSQL sia in esecuzione e che le credenziali in `config.toml` siano corrette:")
        print(f"  - Host, Port, User, Password, DBName")
        print(f"Dettagli errore: {e}")
        return  # Esce se la connessione fallisce

    # 2. Creazione tabelle
    print("\nCreazione tabelle (se non esistono)...")
    # Importa i modelli per la creazione di tutte le tabelle (incluso TeamMapping)
    from models import Feature, Fixture, Odds, TeamMapping  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelle create con successo (se non esistevano): fixtures, odds, features, team_mappings.")


if __name__ == "__main__":
    main()
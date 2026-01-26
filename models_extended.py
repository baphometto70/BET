#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCHEMA DATABASE ESTESO - Tutti i dati possibili
- Match results completi
- Lineups (formazioni)
- Goalscorers (marcatori)
- Match stats (shots, corners, cards, possesso)
- Player stats
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base, engine
# Import modelli base per le foreign keys
from models import Fixture


class MatchResult(Base):
    """Risultati dettagliati delle partite (2025-2026)"""
    __tablename__ = "match_results"

    match_id = Column(String, ForeignKey("fixtures.match_id"), primary_key=True)

    # Risultati
    ft_home_goals = Column(Integer)  # Full time
    ft_away_goals = Column(Integer)
    ht_home_goals = Column(Integer, nullable=True)  # Half time
    ht_away_goals = Column(Integer, nullable=True)

    # Winner
    winner = Column(String(10), nullable=True)  # 'HOME', 'AWAY', 'DRAW'

    # Metadata
    referee = Column(String, nullable=True)
    venue = Column(String, nullable=True)
    attendance = Column(Integer, nullable=True)

    # Relationships
    fixture = relationship("Fixture", backref="result")
    stats = relationship("MatchStats", back_populates="match_result", uselist=False)
    goalscorers = relationship("Goalscorer", back_populates="match_result")


class MatchStats(Base):
    """Statistiche dettagliate partita (shots, corners, cards, possesso)"""
    __tablename__ = "match_stats"

    match_id = Column(String, ForeignKey("match_results.match_id"), primary_key=True)

    # Shots
    shots_home = Column(Integer, nullable=True)
    shots_away = Column(Integer, nullable=True)
    shots_on_target_home = Column(Integer, nullable=True)
    shots_on_target_away = Column(Integer, nullable=True)
    shots_inside_box_home = Column(Integer, nullable=True)
    shots_inside_box_away = Column(Integer, nullable=True)
    shots_outside_box_home = Column(Integer, nullable=True)
    shots_outside_box_away = Column(Integer, nullable=True)

    # Possesso
    possession_home = Column(Float, nullable=True)  # Percentuale 0-100
    possession_away = Column(Float, nullable=True)

    # Passaggi
    passes_home = Column(Integer, nullable=True)
    passes_away = Column(Integer, nullable=True)
    passes_accurate_home = Column(Integer, nullable=True)
    passes_accurate_away = Column(Integer, nullable=True)
    pass_accuracy_home = Column(Float, nullable=True)  # Percentuale
    pass_accuracy_away = Column(Float, nullable=True)

    # Corners
    corners_home = Column(Integer, nullable=True)
    corners_away = Column(Integer, nullable=True)

    # Falli e cartellini
    fouls_home = Column(Integer, nullable=True)
    fouls_away = Column(Integer, nullable=True)
    yellow_cards_home = Column(Integer, nullable=True)
    yellow_cards_away = Column(Integer, nullable=True)
    red_cards_home = Column(Integer, nullable=True)
    red_cards_away = Column(Integer, nullable=True)

    # Fuorigioco
    offsides_home = Column(Integer, nullable=True)
    offsides_away = Column(Integer, nullable=True)

    # Parate portiere
    saves_home = Column(Integer, nullable=True)
    saves_away = Column(Integer, nullable=True)

    # Advanced metrics
    tackles_home = Column(Integer, nullable=True)
    tackles_away = Column(Integer, nullable=True)
    interceptions_home = Column(Integer, nullable=True)
    interceptions_away = Column(Integer, nullable=True)
    clearances_home = Column(Integer, nullable=True)
    clearances_away = Column(Integer, nullable=True)

    # Relationship
    match_result = relationship("MatchResult", back_populates="stats")


class Lineup(Base):
    """Formazioni (11 titolari + panchina)"""
    __tablename__ = "lineups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, ForeignKey("fixtures.match_id"), index=True)
    team = Column(String)  # 'HOME' o 'AWAY'

    player_name = Column(String)
    player_number = Column(Integer, nullable=True)
    position = Column(String, nullable=True)  # GK, DEF, MID, FWD
    is_starter = Column(Boolean, default=True)  # True = titolare, False = panchina

    # Se è entrato/uscito
    substituted_in = Column(Integer, nullable=True)  # Minuto entrata
    substituted_out = Column(Integer, nullable=True)  # Minuto uscita

    # Yellow/Red cards
    yellow_card = Column(Boolean, default=False)
    red_card = Column(Boolean, default=False)
    card_minute = Column(Integer, nullable=True)


class Goalscorer(Base):
    """Marcatori e assist"""
    __tablename__ = "goalscorers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, ForeignKey("match_results.match_id"), index=True)

    team = Column(String)  # 'HOME' o 'AWAY'
    player_name = Column(String)
    minute = Column(Integer)
    is_penalty = Column(Boolean, default=False)
    is_own_goal = Column(Boolean, default=False)
    assist_by = Column(String, nullable=True)

    # Relationship
    match_result = relationship("MatchResult", back_populates="goalscorers")


class PlayerSeason(Base):
    """Statistiche stagionali giocatore (gol, assist, presenze)"""
    __tablename__ = "player_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_name = Column(String, index=True)
    team = Column(String, index=True)
    season = Column(String, index=True)  # '2025' o '2026'
    league = Column(String, index=True)

    # Presenze
    appearances = Column(Integer, default=0)
    minutes_played = Column(Integer, default=0)

    # Gol e assist
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    penalties_scored = Column(Integer, default=0)

    # Cartellini
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)


class TeamForm(Base):
    """Form recente squadra (ultimi 5-10 match) - CALCOLATA"""
    __tablename__ = "team_form"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_name = Column(String, index=True)
    league_code = Column(String(10), index=True)
    as_of_date = Column(Date, index=True)  # Data di riferimento

    # Ultimi 5 match (tutti)
    last5_wins = Column(Integer, default=0)
    last5_draws = Column(Integer, default=0)
    last5_losses = Column(Integer, default=0)
    last5_goals_for = Column(Integer, default=0)
    last5_goals_against = Column(Integer, default=0)
    last5_points = Column(Integer, default=0)

    # Ultimi 5 match (solo casa)
    last5_home_wins = Column(Integer, default=0)
    last5_home_draws = Column(Integer, default=0)
    last5_home_losses = Column(Integer, default=0)
    last5_home_gf = Column(Integer, default=0)
    last5_home_ga = Column(Integer, default=0)

    # Ultimi 5 match (solo trasferta)
    last5_away_wins = Column(Integer, default=0)
    last5_away_draws = Column(Integer, default=0)
    last5_away_losses = Column(Integer, default=0)
    last5_away_gf = Column(Integer, default=0)
    last5_away_ga = Column(Integer, default=0)

    # Streak
    current_streak = Column(Integer, default=0)  # +3 = 3 vittorie, -2 = 2 sconfitte
    unbeaten_streak = Column(Integer, default=0)


class HeadToHead(Base):
    """Storico scontri diretti tra due squadre"""
    __tablename__ = "head_to_head"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_home = Column(String, index=True)
    team_away = Column(String, index=True)
    league_code = Column(String(10), index=True)

    # Ultimi N scontri (tutti)
    total_matches = Column(Integer, default=0)
    home_wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    away_wins = Column(Integer, default=0)

    # Gol
    avg_goals_home = Column(Float, default=0.0)
    avg_goals_away = Column(Float, default=0.0)
    avg_total_goals = Column(Float, default=0.0)
    btts_count = Column(Integer, default=0)  # Both teams to score

    # Last update
    last_updated = Column(Date, default=datetime.utcnow)


# ========================================
# CREA TUTTE LE TABELLE
# ========================================
def create_extended_tables():
    """Crea tutte le tabelle estese nel database"""
    print("🔧 Creazione tabelle estese...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelle create!")


if __name__ == "__main__":
    create_extended_tables()

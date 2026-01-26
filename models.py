#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Date,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


class Fixture(Base):
    __tablename__ = "fixtures"

    match_id = Column(String, primary_key=True, index=True)
    date = Column(Date, index=True)
    time = Column(String(5))  # HH:MM
    time_local = Column(String(5))
    league = Column(String, index=True)
    league_code = Column(String(10), index=True)
    home = Column(String)
    away = Column(String)
    result_home_goals = Column(Integer, nullable=True)  # Risultato finale
    result_away_goals = Column(Integer, nullable=True)  # Risultato finale

    # Relationships
    feature = relationship("Feature", back_populates="fixture", uselist=False, cascade="all, delete-orphan")
    odds = relationship("Odds", back_populates="fixture", uselist=False, cascade="all, delete-orphan")


class Feature(Base):
    __tablename__ = "features"

    match_id = Column(String, ForeignKey("fixtures.match_id"), primary_key=True)
    
    xg_for_home = Column(Float, nullable=True)
    xg_against_home = Column(Float, nullable=True)
    xg_for_away = Column(Float, nullable=True)
    xg_against_away = Column(Float, nullable=True)
    # Origine dati xG: 'understat' | 'odds' | 'fallback'
    xg_source_home = Column(String(50), nullable=True)
    xg_source_away = Column(String(50), nullable=True)
    # Confidenza stimata a livello di feature (percentuale 0-100)
    xg_confidence = Column(Float, nullable=True)
    
    rest_days_home = Column(Integer, nullable=True)
    rest_days_away = Column(Integer, nullable=True)
    injuries_key_home = Column(Integer, nullable=True)
    injuries_key_away = Column(Integer, nullable=True)
    derby_flag = Column(Integer, default=0)
    europe_flag_home = Column(Integer, default=0)
    europe_flag_away = Column(Integer, default=0)
    meteo_flag = Column(Integer, default=0)
    style_ppda_home = Column(Float, nullable=True)
    style_ppda_away = Column(Float, nullable=True)
    travel_km_away = Column(Float, nullable=True)

    fixture = relationship("Fixture", back_populates="feature")


class Odds(Base):
    __tablename__ = "odds"

    match_id = Column(String, ForeignKey("fixtures.match_id"), primary_key=True)
    
    odds_1 = Column(Float, nullable=True)
    odds_x = Column(Float, nullable=True)
    odds_2 = Column(Float, nullable=True)
    odds_ou25_over = Column(Float, nullable=True)
    odds_ou25_under = Column(Float, nullable=True)
    line_ou = Column(String(5), default="2.5")

    fixture = relationship("Fixture", back_populates="odds")


class TeamMapping(Base):
    __tablename__ = "team_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String, nullable=False, index=True)
    understat_name = Column(String, nullable=True)
    fbref_id = Column(String, nullable=True)
    fbref_name = Column(String, nullable=True)
    league_code = Column(String(10), nullable=False, index=True)
    source = Column(String(50), default="football-data.co.uk", nullable=False)
    last_updated = Column(Date, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "source_name", "league_code", "source", name="uq_source_name_league_source"
        ),
    )


class HistoricalMatch(Base):
    """
    Storico partite per training ML (1X2, OU, BTTS).
    Popolato da data/historical_dataset.csv|historical_1x2.csv.
    """
    __tablename__ = "historical_matches"

    match_id = Column(String, primary_key=True, index=True)
    date = Column(Date, index=True)
    time_local = Column(String(5))
    league = Column(String, index=True)
    home = Column(String)
    away = Column(String)
    ft_home_goals = Column(Integer)
    ft_away_goals = Column(Integer)

    odds_1 = Column(Float, nullable=True)
    odds_x = Column(Float, nullable=True)
    odds_2 = Column(Float, nullable=True)

    xg_for_home = Column(Float, nullable=True)
    xg_against_home = Column(Float, nullable=True)
    xg_for_away = Column(Float, nullable=True)
    xg_against_away = Column(Float, nullable=True)

    rest_days_home = Column(Integer, nullable=True)
    rest_days_away = Column(Integer, nullable=True)
    derby_flag = Column(Integer, default=0)
    europe_flag_home = Column(Integer, default=0)
    europe_flag_away = Column(Integer, default=0)
    meteo_flag = Column(Integer, default=0)
    style_ppda_home = Column(Float, nullable=True)
    style_ppda_away = Column(Float, nullable=True)
    travel_km_away = Column(Float, nullable=True)

    target_ou25 = Column(Integer, nullable=True)  # 1=Over,0=Under
    target_btts = Column(Integer, nullable=True)  # 1=Goal,0=NoGoal
    target_1x2 = Column(Integer, nullable=True)   # 1=home,0=draw,-1=away


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, ForeignKey("fixtures.match_id"), nullable=False, index=True)
    prediction_date = Column(Date, default=datetime.utcnow, index=True)
    
    # 1X2
    pick_1x2 = Column(String(5)) # "1", "X", "2"
    confidence_1x2 = Column(String(20)) # "High", "Medium", "Low"
    prob_1 = Column(Float)
    prob_x = Column(Float)
    prob_2 = Column(Float)
    
    # Over/Under 2.5
    pick_ou = Column(String(20)) # "OVER 2.5", "UNDER 2.5"
    prob_over = Column(Float)
    prob_under = Column(Float)
    
    # BTTS
    pick_btts = Column(String(20)) # "GOAL", "NOGOAL"
    prob_btts_yes = Column(Float)
    
    # New Metrics
    data_quality = Column(String(20)) # "High", "Medium", "Low"
    consensus_score = Column(Integer)
    
    # Extra Markets
    prob_mg_1_3 = Column(Float)
    prob_mg_2_4 = Column(Float)
    prob_combo_1_over = Column(Float)     # 1 + Over 1.5
    prob_combo_1x_over = Column(Float)    # 1X + Over 1.5
    
    # Metadata
    created_at = Column(Date, default=datetime.utcnow)

    fixture = relationship("Fixture")

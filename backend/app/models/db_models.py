import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    email = Column(String, nullable=True)
    telegram_chat_id = Column(String, nullable=True)

    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")

class Station(Base):
    __tablename__ = "stations"

    name = Column(String, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    classification = Column(String, nullable=False)

    forecasts = relationship("StationForecast", back_populates="station", cascade="all, delete-orphan")
    watchlists = relationship("Watchlist", back_populates="station", cascade="all, delete-orphan")

class StationForecast(Base):
    __tablename__ = "station_forecasts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    station_name = Column(String, ForeignKey("stations.name", ondelete="CASCADE"), nullable=False, index=True)
    time = Column(String, nullable=False)
    temp = Column(Float, nullable=False)
    rh = Column(Float, nullable=False)
    wind_speed = Column(Float, nullable=False)
    wind_dir = Column(Float, nullable=False)
    press = Column(Float, nullable=False)
    wave_h = Column(Float, nullable=False)
    wave_direction = Column(Float, nullable=False)
    wave_p = Column(Float, nullable=False)
    current_vel = Column(Float, nullable=False)
    current_dir = Column(Float, nullable=False)
    sst = Column(Float, nullable=False)
    storm_severity = Column(Integer, nullable=False)
    storm_severity_name = Column(String, nullable=False)
    climatology_prior = Column(Float, nullable=False)
    pred_rain = Column(Float, nullable=False)
    pred_wind = Column(Float, nullable=False)
    pred_pres = Column(Float, nullable=False)
    is_fallback = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    station = relationship("Station", back_populates="forecasts")

class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    station_name = Column(String, ForeignKey("stations.name", ondelete="CASCADE"), nullable=False, index=True)

    user = relationship("User", back_populates="watchlists")
    station = relationship("Station", back_populates="watchlists")

    # Composite unique constraint to avoid duplicate subscriptions
    __table_args__ = (UniqueConstraint('user_id', 'station_name', name='_user_station_uc'),)

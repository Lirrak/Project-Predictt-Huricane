import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Default to SQLite local database file if no PostgreSQL URL is provided
# This allows flawless local testing out of the box while supporting PostgreSQL in production
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./weather.db")

if DATABASE_URL.startswith("sqlite"):
    # SQLite requires check_same_thread=False for multi-threaded FastAPI handlers
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

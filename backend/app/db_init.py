from app.database import Base, engine, SessionLocal
from app.models.db_models import Station
from app.services.weather_service import STATIONS

def init_db():
    """Creates database tables and seeds the 37 stations if the table is empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Station).count() == 0:
            print("Database empty. Seeding 37 meteorological stations...")
            for name, data in STATIONS.items():
                station = Station(
                    name=name,
                    latitude=data["lat"],
                    longitude=data["lon"],
                    classification=data["classification"]
                )
                db.add(station)
            db.commit()
            print("Successfully seeded 37 stations!")
        else:
            print("Database already contains stations. Skipping seed.")
    except Exception as e:
        print(f"Error initializing or seeding database: {e}")
        db.rollback()
    finally:
        db.close()

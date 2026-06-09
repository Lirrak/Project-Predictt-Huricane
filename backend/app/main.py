import time
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.db_init import init_db
from app.models.db_models import Station, StationForecast, User, Watchlist
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.services.weather_service import (
    STATIONS,
    SEVERITY_NAMES,
    fetch_all_stations_raw_data,
    process_station_data,
    generate_prediction_input,
)
from app.models.model_loader import models_loader
from app.services.forecast_updater import update_forecasts_in_db

app = FastAPI(
    title="Biển Đông Advanced Forecast Backend",
    description="FastAPI Backend with Authentication, Database caching, Watchlists, and Background Forecast updates",
    version="1.2.0",
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory store for the Raspberry Pi heartbeat
heartbeat_store = {
    "status": "UNKNOWN",
    "timestamp": 0.0,
    "message": ""
}

# Pydantic Schemas
class PredictRequest(BaseModel):
    station_name: str = "all"
    simulated_storm_level: Optional[int] = None

class HeartbeatRequest(BaseModel):
    status: Optional[str] = "ONLINE"
    message: Optional[str] = "ping"

class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class WatchlistToggleRequest(BaseModel):
    station_name: str

async def run_periodic_updates():
    """Infinite background loop updating forecasts from Open-Meteo and running predictions every 3 hours."""
    await asyncio.sleep(2)
    while True:
        try:
            db = SessionLocal()
            try:
                print("Starting automatic periodic meteorology and model forecast update...")
                # Pass the DB instance to update forecasts and optionally trigger alert alerts
                from app.services.alert_service import check_and_trigger_alerts
                
                # Capture the current forecasts state before update to compare for upgrades
                old_severities = {f.station_name: f.storm_severity for f in db.query(StationForecast).all()}
                
                update_forecasts_in_db(db)
                
                # Check for upgrades and trigger alerts
                check_and_trigger_alerts(db, old_severities)
                print("Automatic periodic update completed successfully.")
            finally:
                db.close()
        except Exception as e:
            print(f"Error in automatic periodic background task: {e}")
        
        # Sleep for 3 hours
        await asyncio.sleep(3 * 3600)

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(run_periodic_updates())

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Biển Đông Advanced Forecast API",
        "version": "1.2.0",
        "status": "active"
    }

@app.post("/api/ml/reload")
def reload_models(request: Request):
    """
    Triggers an on-the-fly hot reload of the XGBoost ML models from disk.
    Only accessible from localhost for security reasons.
    """
    client_host = request.client.host
    if client_host not in ["127.0.0.1", "localhost", "::1"]:
        raise HTTPException(status_code=403, detail="Forbidden: Only localhost can trigger model reload.")
    
    models_loader.is_loaded = False
    success = models_loader.load_models()
    if success:
        return {"status": "success", "message": "ML models hot-reloaded successfully on-the-fly!"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to reload models: {models_loader.error_msg}")

@app.get("/api/ml/audit")
def get_ml_audit():
    """
    Returns the pre-computed ML model audit results from disk.
    """
    import os
    import json
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    audit_json_path = os.path.join(project_root, "data", "audit_results.json")
    
    if not os.path.exists(audit_json_path):
        # If the file does not exist, run the audit script to generate it
        try:
            import subprocess
            import sys
            python_exe = sys.executable or "python"
            script_path = os.path.join(project_root, "src", "audit_model.py")
            subprocess.run([python_exe, script_path], check=True, timeout=30)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate audit results: {e}")
            
    if not os.path.exists(audit_json_path):
        raise HTTPException(status_code=404, detail="Audit results file not found.")
        
    try:
        with open(audit_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read audit results: {e}")

# --- AUTH ENDPOINTS ---

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Registers a new user account with hashed password and optional alert channels.
    """
    # Check if username exists
    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    hashed = get_password_hash(payload.password)
    user = User(
        username=payload.username,
        hashed_password=hashed,
        email=payload.email,
        telegram_chat_id=payload.telegram_chat_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_access_token(data={"sub": user.username})
    return {
        "message": "User registered successfully",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "telegram_chat_id": user.telegram_chat_id
        }
    }

@app.post("/api/auth/login")
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticates a user via JSON payload and returns a Bearer access token.
    """
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "telegram_chat_id": user.telegram_chat_id
        }
    }

@app.post("/api/auth/login/form")
def login_user_form(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Standard OAuth2 compatible token login endpoint supporting form-data.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = create_access_token(data={"sub": user.username})
    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.get("/api/auth/me")
def get_me(user: User = Depends(get_current_user)):
    """
    Returns the current user profile context based on token.
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "telegram_chat_id": user.telegram_chat_id
    }

# --- WATCHLIST ENDPOINTS ---

@app.get("/api/watchlist")
def get_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns the list of stations that the current logged-in user is watching.
    """
    items = db.query(Watchlist).filter(Watchlist.user_id == user.id).all()
    return [item.station_name for item in items]

@app.post("/api/watchlist/toggle")
def toggle_watchlist_station(payload: WatchlistToggleRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Adds or removes a station from the current logged-in user's watchlist.
    """
    # Validate station exists
    station = db.query(Station).filter(Station.name == payload.station_name).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    existing = db.query(Watchlist).filter(
        Watchlist.user_id == user.id,
        Watchlist.station_name == payload.station_name
    ).first()

    if existing:
        # Remove subscription
        db.delete(existing)
        db.commit()
        is_watching = False
    else:
        # Add subscription
        watchlist_item = Watchlist(user_id=user.id, station_name=payload.station_name)
        db.add(watchlist_item)
        db.commit()
        is_watching = True

    # Return full updated list
    items = db.query(Watchlist).filter(Watchlist.user_id == user.id).all()
    return {
        "station_name": payload.station_name,
        "is_watching": is_watching,
        "watchlist": [item.station_name for item in items]
    }

# --- STATIONS & FORECAST ENDPOINTS ---

@app.get("/api/stations")
def get_stations(db: Session = Depends(get_db)):
    """
    Returns the list of all 37 meteorological stations read from the database.
    """
    stations = db.query(Station).all()
    return [
        {
            "name": st.name,
            "latitude": st.latitude,
            "longitude": st.longitude,
            "classification": st.classification
        }
        for st in stations
    ]

@app.get("/api/stations/forecast")
def get_stations_forecast(station_name: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Reads pre-calculated forecasts directly from the database for sub-50ms speed.
    """
    start_time = time.time()
    
    query = db.query(StationForecast)
    if station_name:
        query = query.filter(StationForecast.station_name == station_name)
    
    forecasts = query.all()

    if not forecasts:
        print("No forecasts in DB. Running fallback on-the-fly calculation...")
        update_forecasts_in_db(db)
        
        query = db.query(StationForecast)
        if station_name:
            query = query.filter(StationForecast.station_name == station_name)
        forecasts = query.all()

    response_data = [
        {
            "station_name": f.station_name,
            "latitude": f.station.latitude if f.station else None,
            "longitude": f.station.longitude if f.station else None,
            "classification": f.station.classification if f.station else "Land/Coastal",
            "time": f.time,
            "temp": f.temp,
            "rh": f.rh,
            "wind_speed": f.wind_speed,
            "wind_dir": f.wind_dir,
            "press": f.press,
            "wave_h": f.wave_h,
            "wave_direction": f.wave_direction,
            "wave_p": f.wave_p,
            "current_vel": f.current_vel,
            "current_dir": f.current_dir,
            "sst": f.sst,
            "storm_severity": f.storm_severity,
            "storm_severity_name": f.storm_severity_name,
            "climatology_prior": f.climatology_prior,
            "pred_rain": f.pred_rain,
            "pred_wind": f.pred_wind,
            "pred_pres": f.pred_pres,
            "is_fallback": f.is_fallback,
            "updated_at_utc": f.updated_at.strftime("%Y-%m-%d %H:%M:%S")
        }
        for f in forecasts
    ]

    duration_ms = (time.time() - start_time) * 1000
    print(f"Served /api/stations/forecast in {duration_ms:.2f}ms")

    if station_name:
        if not response_data:
            raise HTTPException(status_code=404, detail=f"No forecast found for station '{station_name}'")
        return response_data[0]
        
    return response_data

@app.post("/api/forecast/predict")
def predict_forecast(payload: PredictRequest):
    """
    Receives custom simulation data or station name and returns real-time forecasts on-the-fly.
    """
    station_name = payload.station_name
    simulated_storm = payload.simulated_storm_level

    if simulated_storm is not None and (simulated_storm < 0 or simulated_storm > 5):
        raise HTTPException(status_code=400, detail="Simulated storm level must be between 0 and 5.")

    raw_w_list, raw_m_list = fetch_all_stations_raw_data()
    is_valid_w = isinstance(raw_w_list, list) and len(raw_w_list) == len(STATIONS)
    is_valid_m = isinstance(raw_m_list, list) and len(raw_m_list) == len(STATIONS)

    results = []
    for idx, name in enumerate(STATIONS):
        if station_name != "all" and name != station_name:
            continue

        coords = STATIONS[name]
        station_w = raw_w_list[idx] if is_valid_w else None
        station_m = raw_m_list[idx] if is_valid_m else None

        df_raw, is_fallback = process_station_data(name, coords, station_w, station_m, simulated_storm)
        df_input, row_now, storm_severity, climatology_prior = generate_prediction_input(
            name, coords, df_raw, simulated_storm
        )

        pred_rain, pred_wind, pred_pres = models_loader.predict(df_input, row_now)

        results.append({
            "station_name": name,
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "classification": coords["classification"],
            "time": row_now["time"].strftime("%Y-%m-%d %H:%M"),
            "temp": float(row_now["temp_2m"]),
            "rh": float(row_now["rh_2m"]),
            "wind_speed": float(row_now["wind_speed"]),
            "wind_dir": float(row_now["wind_dir"]),
            "press": float(row_now["press_hpa"]),
            "wave_h": float(row_now["wave_height"]),
            "wave_direction": float(row_now["wave_direction"]),
            "wave_p": float(row_now["wave_period"]),
            "current_vel": float(row_now["ocean_current_velocity"]),
            "current_dir": float(row_now["ocean_current_direction"]),
            "sst": float(row_now["sea_surface_temperature"]),
            "storm_severity": int(storm_severity),
            "storm_severity_name": SEVERITY_NAMES.get(storm_severity, "Bình thường"),
            "climatology_prior": float(climatology_prior),
            "pred_rain": float(pred_rain),
            "pred_wind": float(pred_wind),
            "pred_pres": float(pred_pres),
            "is_fallback": is_fallback
        })

    if station_name != "all" and not results:
        raise HTTPException(status_code=404, detail=f"Station '{station_name}' not found.")

    return results[0] if station_name != "all" else results

@app.post("/api/iot/heartbeat")
async def receive_heartbeat(request: Request, payload: Optional[HeartbeatRequest] = None):
    """
    Receives direct active state signals from Raspberry Pi.
    """
    message = "ping"
    status = "ONLINE"

    body = await request.body()
    decoded_body = body.decode("utf-8").strip()

    if decoded_body == "ping":
        message = "ping"
    elif payload:
        status = payload.status or "ONLINE"
        message = payload.message or "ping"
    elif decoded_body:
        message = decoded_body

    heartbeat_store["status"] = status
    heartbeat_store["timestamp"] = time.time()
    heartbeat_store["message"] = message

    return {
        "status": "success",
        "received": {
            "status": status,
            "message": message,
            "timestamp": heartbeat_store["timestamp"]
        }
    }

@app.get("/api/iot/status")
def get_iot_status():
    """
    Returns the Raspberry Pi connectivity status.
    """
    if heartbeat_store["timestamp"] == 0.0:
        return {
            "status": "UNKNOWN",
            "seconds_since_last_heartbeat": None,
            "last_heartbeat_time": None
        }

    time_diff = time.time() - heartbeat_store["timestamp"]
    status = "ONLINE" if time_diff < 40 else "OFFLINE"

    return {
        "status": status,
        "seconds_since_last_heartbeat": int(time_diff),
        "last_heartbeat_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(heartbeat_store["timestamp"]))
    }

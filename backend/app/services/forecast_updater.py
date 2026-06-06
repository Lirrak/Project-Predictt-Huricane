import datetime
from sqlalchemy.orm import Session
from app.models.db_models import StationForecast, Station
from app.services.weather_service import (
    STATIONS,
    SEVERITY_NAMES,
    fetch_all_stations_raw_data,
    process_station_data,
    generate_prediction_input,
)
from app.models.model_loader import models_loader

def update_forecasts_in_db(db: Session):
    """
    Fetches raw weather data from Open-Meteo, calculates physical characteristics,
    predicts using XGBoost, and updates the database with the latest forecasts.
    """
    print(f"[{datetime.datetime.now()}] Fetching Open-Meteo weather and marine data for all stations...")
    raw_w_list, raw_m_list = fetch_all_stations_raw_data()
    
    is_valid_w = isinstance(raw_w_list, list) and len(raw_w_list) == len(STATIONS)
    is_valid_m = isinstance(raw_m_list, list) and len(raw_m_list) == len(STATIONS)
    
    if not is_valid_w or not is_valid_m:
        print(f"[{datetime.datetime.now()}] Warning: Open-Meteo API data is incomplete or unavailable. Using fallbacks.")

    updated_count = 0
    for idx, name in enumerate(STATIONS):
        coords = STATIONS[name]
        station_w = raw_w_list[idx] if is_valid_w else None
        station_m = raw_m_list[idx] if is_valid_m else None

        try:
            # Process raw weather and marine data (with automatic offline fallback if API is down)
            df_raw, is_fallback = process_station_data(name, coords, station_w, station_m, simulated_storm_level=None)

            # Generate 45 physical atmospheric-oceanic features
            df_input, row_now, storm_severity, climatology_prior = generate_prediction_input(
                name, coords, df_raw, simulated_storm_level=None
            )

            # Run model predictions using loaded XGBoost models
            pred_rain, pred_wind, pred_pres = models_loader.predict(df_input, row_now)

            # Delete any existing forecast for this station to keep database clean and optimized
            db.query(StationForecast).filter(StationForecast.station_name == name).delete()

            # Insert new forecast
            forecast = StationForecast(
                station_name=name,
                time=row_now["time"].strftime("%Y-%m-%d %H:%M"),
                temp=float(row_now["temp_2m"]),
                rh=float(row_now["rh_2m"]),
                wind_speed=float(row_now["wind_speed"]),
                wind_dir=float(row_now["wind_dir"]),
                press=float(row_now["press_hpa"]),
                wave_h=float(row_now["wave_height"]),
                wave_direction=float(row_now["wave_direction"]),
                wave_p=float(row_now["wave_period"]),
                current_vel=float(row_now["ocean_current_velocity"]),
                current_dir=float(row_now["ocean_current_direction"]),
                sst=float(row_now["sea_surface_temperature"]),
                storm_severity=int(storm_severity),
                storm_severity_name=SEVERITY_NAMES.get(storm_severity, "Bình thường"),
                climatology_prior=float(climatology_prior),
                pred_rain=float(pred_rain),
                pred_wind=float(pred_wind),
                pred_pres=float(pred_pres),
                is_fallback=is_fallback
            )
            
            db.add(forecast)
            updated_count += 1
        except Exception as e:
            print(f"Error updating forecast for station {name}: {e}")
            continue

    db.commit()
    print(f"[{datetime.datetime.now()}] Successfully updated {updated_count}/37 station forecasts in database.")

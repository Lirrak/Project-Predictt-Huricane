import os
from xgboost import XGBRegressor

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", ".."))

MODEL_JSON_RAIN = os.path.join(PROJECT_ROOT, "models", "xgboost_rain_model.json")
MODEL_JSON_WIND = os.path.join(PROJECT_ROOT, "models", "xgboost_wind_model.json")
MODEL_JSON_PRES = os.path.join(PROJECT_ROOT, "models", "xgboost_pres_model.json")

class ModelLoader:
    def __init__(self):
        self.model_rain = None
        self.model_wind = None
        self.model_pres = None
        self.is_loaded = False
        self.error_msg = None

    def load_models(self):
        if self.is_loaded:
            return True
            
        try:
            if not os.path.exists(MODEL_JSON_RAIN):
                raise FileNotFoundError(f"Rain model file not found: {MODEL_JSON_RAIN}")
            if not os.path.exists(MODEL_JSON_WIND):
                raise FileNotFoundError(f"Wind model file not found: {MODEL_JSON_WIND}")
            if not os.path.exists(MODEL_JSON_PRES):
                raise FileNotFoundError(f"Pressure model file not found: {MODEL_JSON_PRES}")

            self.model_rain = XGBRegressor()
            self.model_rain.load_model(MODEL_JSON_RAIN)
            
            self.model_wind = XGBRegressor()
            self.model_wind.load_model(MODEL_JSON_WIND)
            
            self.model_pres = XGBRegressor()
            self.model_pres.load_model(MODEL_JSON_PRES)
            
            self.is_loaded = True
            self.error_msg = None
            return True
        except Exception as e:
            import traceback
            self.error_msg = traceback.format_exc()
            self.is_loaded = False
            return False

    def predict(self, df_input, row_now):
        """Predict rain, wind, and pressure using the loaded models or fallbacks."""
        if not self.is_loaded:
            # Attempt to load
            success = self.load_models()
            if not success:
                # Use fallback from row_now
                pred_rain = max(0.0, float(row_now['precipitation']))
                pred_wind = float(row_now['wind_speed'])
                pred_pres = float(row_now['press_hpa'])
                return pred_rain, pred_wind, pred_pres

        try:
            pred_rain = max(0.0, float(self.model_rain.predict(df_input)[0]))
            pred_wind_ms = max(0.0, float(self.model_wind.predict(df_input)[0]))
            pred_wind = pred_wind_ms * 3.6  # m/s -> km/h
            pred_pres_pa = float(self.model_pres.predict(df_input)[0])
            pred_pres = pred_pres_pa / 100.0  # Pa -> hPa
        except Exception:
            pred_rain = max(0.0, float(row_now['precipitation']))
            pred_wind = float(row_now['wind_speed'])
            pred_pres = float(row_now['press_hpa'])
            
        return pred_rain, pred_wind, pred_pres

# Singleton instance
models_loader = ModelLoader()
# Preload models
models_loader.load_models()

import os
import requests
from sqlalchemy.orm import Session
from app.models.db_models import User, Watchlist, StationForecast

# Configure alert mock channels/keys (for demonstration/production)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "mock_bot_token_lirrak_project")

def send_mock_email(to_email: str, subject: str, body: str):
    """Simulates sending an Email via SMTP (perfect for secure sandboxes)."""
    print(f"\n[ALERT - EMAIL SENT TO {to_email}]")
    print(f"Subject: {subject}")
    print(f"Body: {body}\n")
    return True

def send_mock_telegram(chat_id: str, text: str):
    """
    Simulates sending a Telegram alert.
    If a real TELEGRAM_BOT_TOKEN is provided, it tries to send a real message.
    """
    print(f"\n[ALERT - TELEGRAM SENT TO CHAT {chat_id}]")
    print(f"Message: {text}\n")
    
    if TELEGRAM_BOT_TOKEN and not TELEGRAM_BOT_TOKEN.startswith("mock_"):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=5)
        except Exception as e:
            print(f"Error sending real Telegram message: {e}")
    return True

def check_and_trigger_alerts(db: Session, old_severities: dict):
    """
    Compares the newly calculated station severities against the pre-update state.
    Triggers automated Email / Telegram alerts on storm classification upgrades (>= 1).
    """
    print("Checking for storm alerts and subscription updates...")
    current_forecasts = db.query(StationForecast).all()

    for forecast in current_forecasts:
        name = forecast.station_name
        new_severity = forecast.storm_severity
        old_severity = old_severities.get(name, 0)

        # Trigger condition: Severity has increased, and is now classified as a storm/depression (>= 1)
        if new_severity > old_severity and new_severity >= 1:
            print(f"🚨 STORM UPGRADE DETECTED at Station '{name}': Cấp {old_severity} -> Cấp {new_severity} ({forecast.storm_severity_name})!")
            
            # Find all users subscribed to this station
            watchers = db.query(User).join(Watchlist).filter(Watchlist.station_name == name).all()
            
            if not watchers:
                print(f"No active watchers subscribed to Station '{name}'.")
                continue
                
            print(f"Triggering alerts for {len(watchers)} watchers...")
            for user in watchers:
                alert_subject = f"⚠️ CẢNH BÁO THIÊN TAI KHẨN CẤP - Trạm {name}"
                alert_body = (
                    f"Xin chào {user.username},\n\n"
                    f"Hệ thống khí tượng Biển Đông Advanced phát hiện diễn biến bão cực kỳ nguy hiểm:\n"
                    f"- Trạm giám sát: {name}\n"
                    f"- Diễn biến nâng cấp bão: Cấp {old_severity} ➔ Cấp {new_severity} ({forecast.storm_severity_name})\n"
                    f"- Sức gió hiện tại: {forecast.wind_speed} km/h (Sức gió dự báo 24h: {forecast.pred_wind} km/h)\n"
                    f"- Khí áp bề mặt: {forecast.press} hPa (Áp suất dự báo 24h: {forecast.pred_pres} hPa)\n"
                    f"- Độ cao sóng biển: {forecast.wave_h} mét\n"
                    f"- Thời điểm ghi nhận: {forecast.time}\n\n"
                    f"Vui lòng chủ động cập nhật thông tin và thực hiện các biện pháp ứng phó an toàn khí tượng khẩn cấp!"
                )

                # Trigger Email Channel
                if user.email:
                    send_mock_email(user.email, alert_subject, alert_body)
                    
                # Trigger Telegram Channel
                if user.telegram_chat_id:
                    telegram_text = (
                        f"🚨 *CẢNH BÁO BÃO BIỂN ĐÔNG KHẨN CẤP*\n\n"
                        f"📍 *Trạm:* {name}\n"
                        f"⚠️ *Nâng cấp bão:* Cấp {old_severity} ➔ Cấp {new_severity} (*{forecast.storm_severity_name}*)\n"
                        f"💨 *Sức gió:* {forecast.wind_speed} km/h (Dự báo: {forecast.pred_wind} km/h)\n"
                        f"📉 *Khí áp:* {forecast.press} hPa\n"
                        f"🌊 *Sóng cao:* {forecast.wave_h}m\n\n"
                        f"🔔 _Vui lòng cập nhật ngay sơ đồ an toàn hàng hải!_"
                    )
                    send_mock_telegram(user.telegram_chat_id, telegram_text)

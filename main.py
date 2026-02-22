import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")

def test_conexion():
    print(f"Intentando enviar mensaje al ID: {CHAT_ID}")
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    
    # Mensaje de prueba directo
    data = {"chat_id": CHAT_ID, "text": "✅ Prueba de conexión: El bot Sngre está intentando hablar."}
    
    try:
        r = requests.post(url, json=data)
        print(f"Respuesta de Telegram: {r.text}")
    except Exception as e:
        print(f"Error de red: {e}")

if __name__ == "__main__":
    test_conexion()

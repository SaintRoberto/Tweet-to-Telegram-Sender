import requests
import os
import xml.etree.ElementTree as ET

# Configuración desde tus Secrets de GitHub
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")
USER = os.getenv("TWITTER_USER")

def check_nitter():
    # Usamos una instancia estable de Nitter
    url = f"https://nitter.net/{USER}/rss"
    response = requests.get(url)
    
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        # Tomamos el tweet más reciente
        item = root.find(".//item")
        if item is not None:
            title = item.find("title").text
            link = item.find("link").text
            
            mensaje = f"📢 *Nuevo reporte de {USER}:*\n\n{title}\n\n🔗 {link}"
            send_telegram(mensaje)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    check_nitter()

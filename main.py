import requests
import os
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")
USER = os.getenv("TWITTER_USER")

def check_nitter():
    # Usamos la dirección nitter.net que confirmaste
    url = f"https://nitter.net/{USER}/rss"
    print(f"Buscando tweets en: {url}")
    
    try:
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            item = root.find(".//item")
            
            if item is not None:
                title = item.find("title").text
                link = item.find("link").text
                
                # Convertimos el link a Twitter original para que abra bien en el celular
                link_twitter = link.replace("nitter.net", "twitter.com").replace("#m", "")
                
                mensaje = f"📢 *NUEVO REPORTE:*\n\n{title}\n\n🔗 {link_twitter}"
                send_telegram(mensaje)
            else:
                print("No hay tweets disponibles en este momento.")
        else:
            print(f"Error en Nitter: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload)
    print(f"Respuesta de Telegram: {r.text}")

if __name__ == "__main__":
    check_nitter()

import requests
import os
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")
USER = os.getenv("TWITTER_USER")

def check_nitter():
    # Intentamos con una instancia de Nitter diferente y más estable
    url = f"https://nitter.poast.org/{USER}/rss"
    print(f"Buscando tweets de: {USER}...")
    
    try:
        response = requests.get(url, timeout=15)
        print(f"Respuesta del servidor: {response.status_code}")
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            item = root.find(".//item")
            if item is not None:
                title = item.find("title").text
                link = item.find("link").text
                print(f"¡Tweet encontrado!: {title[:30]}...")
                
                mensaje = f"📢 *Nuevo reporte de {USER}:*\n\n{title}\n\n🔗 {link}"
                send_telegram(mensaje)
            else:
                print("No se encontraron tweets en el RSS.")
        else:
            print("El servidor de Twitter/Nitter está ocupado. Reintentando en la próxima vuelta.")
            
    except Exception as e:
        print(f"Error inesperado: {e}")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload)
    print(f"Resultado Telegram: {r.text}")

if __name__ == "__main__":
    check_nitter()

import requests
import os
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")
USER = os.getenv("TWITTER_USER")

def check_nitter():
    # Lista de servidores alternativos (si uno falla, prueba el otro)
    instancias = [
        f"https://nitter.privacydev.net/{USER}/rss",
        f"https://nitter.poast.org/{USER}/rss",
        f"https://nitter.net/{USER}/rss",
        f"https://xcancel.com/{USER}/rss"
    ]
    
    for url in instancias:
        print(f"Intentando con: {url}")
        try:
            # Añadimos un "User-Agent" para que el servidor no nos bloquee pensando que somos un bot simple
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 200 and len(response.content) > 100:
                root = ET.fromstring(response.content)
                item = root.find(".//item")
                
                if item is not None:
                    title = item.find("title").text
                    link = item.find("link").text
                    link_twitter = link.replace(url.split('/')[2], "twitter.com").replace("#m", "")
                    
                    mensaje = f"📢 *NUEVO REPORTE de {USER}:*\n\n{title}\n\n🔗 {link_twitter}"
                    send_telegram(mensaje)
                    return  # ¡ÉXITO! Salimos del programa.
                else:
                    print("Servidor respondió pero no hay tweets.")
            else:
                print(f"Fallo o respuesta vacía (Código: {response.status_code})")
                
        except Exception as e:
            print(f"Error en esta instancia: {e}")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload)
    print(f"Respuesta de Telegram: {r.text}")

if __name__ == "__main__":
    check_nitter()

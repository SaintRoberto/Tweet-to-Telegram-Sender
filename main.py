import requests
import os
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")

def cargar_lista(archivo):
    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    return []

def es_relevante(texto, palabras_clave):
    texto = texto.lower()
    return any(p in texto for p in palabras_clave)

def check_nitter():
    cuentas = cargar_lista("cuentas.txt")
    palabras = cargar_lista("palabras.txt")
    
    if not cuentas or not palabras:
        print("Error: cuentas.txt o palabras.txt están vacíos.")
        return

    # Memoria de IDs
    if os.path.exists("last_id.txt"):
        with open("last_id.txt", "r") as f:
            enviados = set(f.read().splitlines())
    else:
        enviados = set()

    instancias = ["https://nitter.privacydev.net", "https://nitter.net", "https://nitter.poast.org", "https://xcancel.com"]
    nuevos_ids = list(enviados)

    print(f"Iniciando escaneo de {len(cuentas)} cuentas...")

    for usuario in cuentas:
        exito_usuario = False
        for base_url in instancias:
            if exito_usuario: break
            url = f"{base_url}/{usuario}/rss"
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200 and len(response.content) > 100:
                    root = ET.fromstring(response.content)
                    items = root.findall(".//item")[:3] 
                    
                    for item in items:
                        title = item.find("title").text
                        link = item.find("link").text
                        tweet_id = link.split('/')[-1].split('#')[0]

                        if tweet_id not in enviados:
                            if es_relevante(title, palabras):
                                link_x = f"https://x.com/{usuario}/status/{tweet_id}"
                                send_telegram(link_x)
                                enviados.add(tweet_id)
                                nuevos_ids.append(tweet_id)
                        
                    exito_usuario = True
            except Exception:
                continue

    # Guardar memoria (mantenemos los últimos 200 para evitar spam)
    with open("last_id.txt", "w") as f:
        f.write("\n".join(nuevos_ids[-200:]))

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})

if __name__ == "__main__":
    check_nitter()

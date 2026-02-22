import requests
import os
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")

# Lista de cuentas a vigilar
CUENTAS = ["EmergenciasEc", "segura_ep", "ECU911_", "Cupsfire_gye", "BomberosQuito", "BomberosGYE"]

# Tus palabras clave para filtrar
CATEGORIAS = {
    "lluvia": ["lluvia", "inundacion", "inundación", "deslizamiento", "derrumbe", "desbordamiento", "tormenta", "rayo", "granizada", "aluvion", "aluvión", "deslave", "crecida"],
    "incendio": ["incendio", "fuego", "conato", "forestal", "quema", "maleza"],
    "sismo": ["temblor", "sismo", "terremoto", "telúrico", "colapso"],
    "tsunami": ["tsunami", "olas gigantes", "mar recogido"],
    "sequia": ["sequia", "sequía", "déficit hídrico", "estiaje"]
}

def es_relevante(texto):
    texto = texto.lower()
    for palabras in CATEGORIAS.values():
        if any(p in texto for p in palabras):
            return True
    return False

def check_nitter():
    # Memoria para no repetir
    if os.path.exists("last_id.txt"):
        with open("last_id.txt", "r") as f:
            enviados = f.read().splitlines()
    else:
        enviados = []

    # Instancias de auxilio
    # Lista de servidores alternativos (si uno falla, prueba el otro)
    instancias = [
        f"https://nitter.privacydev.net/{USER}/rss",
        f"https://nitter.poast.org/{USER}/rss",
        f"https://nitter.net/{USER}/rss",
        f"https://xcancel.com/{USER}/rss"
    ]
    nuevos_enviados = enviados.copy()

    for usuario in CUENTAS:
        exito_usuario = False
        for base_url in instancias:
            if exito_usuario: break
            url = f"{base_url}/{usuario}/rss"
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 200 and len(response.content) > 100:
                    root = ET.fromstring(response.content)
                    items = root.findall(".//item")[:5] # Revisa los 5 más nuevos
                    
                    for item in items:
                        title = item.find("title").text
                        link = item.find("link").text
                        tweet_id = link.split('/')[-1].split('#')[0]

                        if tweet_id not in enviados:
                            if es_relevante(title):
                                # Convertimos a URL de X.com limpia (mensaje pelado)
                                link_x = f"https://x.com/{usuario}/status/{tweet_id}"
                                send_telegram(link_x)
                                nuevos_enviados.append(tweet_id)
                        
                    exito_usuario = True
            except Exception:
                continue

    # Guardar memoria (mantenemos los últimos 50)
    with open("last_id.txt", "w") as f:
        f.write("\n".join(nuevos_enviados[-50:]))

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    # Enviamos solo el link
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})

if __name__ == "__main__":
    check_nitter()

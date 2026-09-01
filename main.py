import requests
import os
import re
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")


def cargar_lista(archivo):
    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f:
            return [
                line.strip().lower()
                for line in f
                if line.strip() and not line.lstrip().startswith("#")
            ]
    return []


def cargar_fuentes(archivo="fuentes_rss.txt"):
    if not os.path.exists(archivo):
        return []

    with open(archivo, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]


def es_relevante(texto, palabras_clave):
    texto = texto.lower()
    return any(p in texto for p in palabras_clave)


def esta_excluido(texto, frases_exclusion):
    texto = texto.lower()
    return any(frase in texto for frase in frases_exclusion)


def extraer_tweet_id(link):
    match = re.search(r"/status/(\d+)", link)
    return match.group(1) if match else None


def check_nitter():
    cuentas = cargar_lista("cuentas.txt")
    palabras = cargar_lista("palabras.txt")
    frases_exclusion = cargar_lista("frases_exclusion.txt")
    fuentes = cargar_fuentes()

    if not cuentas or not palabras:
        print("Error: cuentas.txt o palabras.txt están vacíos.")
        return

    if not fuentes:
        print("Error: fuentes_rss.txt está vacío o no existe.")
        return

    if os.path.exists("last_id.txt"):
        with open("last_id.txt", "r", encoding="utf-8") as f:
            historial_ids = [line.strip() for line in f if line.strip()]
    else:
        historial_ids = []

    enviados = set(historial_ids)
    nuevos_ids = list(historial_ids)

    print(f"Iniciando escaneo de {len(cuentas)} cuentas...")
    print(f"Fuentes RSS cargadas: {len(fuentes)}")
    print(f"Frases de exclusión cargadas: {len(frases_exclusion)}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        )
    }

    for usuario in cuentas:
        exito_usuario = False

        for plantilla_url in fuentes:
            if exito_usuario:
                break

            if "{usuario}" not in plantilla_url:
                print(
                    f"Fuente inválida en fuentes_rss.txt "
                    f"(falta {{usuario}}): {plantilla_url}"
                )
                continue

            url = plantilla_url.replace("{usuario}", usuario)

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=10
                )

                print(
                    f"@{usuario} -> {url}: "
                    f"HTTP {response.status_code} "
                    f"({len(response.content)} bytes)"
                )

                if response.status_code != 200:
                    continue

                if len(response.content) <= 100:
                    print(f"Respuesta demasiado corta: {url}")
                    continue

                try:
                    root = ET.fromstring(response.content)
                except ET.ParseError as e:
                    print(f"No es XML/RSS válido en {url}: {e}")
                    continue

                items = root.findall(".//item")

                if not items:
                    print(f"Sin items RSS en {url}")
                    continue

                items = items[:3]

                print(
                    f"Fuente OK para @{usuario}: "
                    f"{len(items)} publicaciones encontradas"
                )

                for item in items:
                    title_element = item.find("title")
                    link_element = item.find("link")
                    description_element = item.find("description")

                    if link_element is None:
                        continue

                    title = (
                        title_element.text
                        if title_element is not None and title_element.text
                        else ""
                    )
                    description = (
                        description_element.text
                        if description_element is not None
                        and description_element.text
                        else ""
                    )
                    link = link_element.text or ""

                    tweet_id = extraer_tweet_id(link)

                    if not tweet_id:
                        print(f"No se pudo extraer tweet ID de: {link}")
                        continue

                    if tweet_id in enviados:
                        continue

                    texto_publicacion = f"{title} {description}"

                    if esta_excluido(
                        texto_publicacion,
                        frases_exclusion
                    ):
                        print(
                            f"EXCLUIDO @{usuario}: "
                            f"{title or description}"
                        )
                        enviados.add(tweet_id)
                        nuevos_ids.append(tweet_id)
                        continue

                    if es_relevante(
                        texto_publicacion,
                        palabras
                    ):
                        link_x = (
                            f"https://x.com/{usuario}/status/{tweet_id}"
                        )

                        send_telegram(link_x)

                        enviados.add(tweet_id)
                        nuevos_ids.append(tweet_id)

                exito_usuario = True

            except requests.RequestException as e:
                print(f"Error HTTP con @{usuario} en {url}: {e}")
                continue
            except Exception as e:
                print(f"Error con @{usuario} en {url}: {e}")
                continue

        if not exito_usuario:
            print(
                f"No se encontró una fuente RSS funcional "
                f"para @{usuario}"
            )

    with open("last_id.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(nuevos_ids[-200:]))


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print(
            "Error: faltan TELEGRAM_TOKEN o TELEGRAM_TO "
            "en las variables de entorno."
        )
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=10
        )

        if response.status_code != 200:
            print(
                f"Error enviando a Telegram: "
                f"HTTP {response.status_code} - "
                f"{response.text[:200]}"
            )
    except requests.RequestException as e:
        print(f"Error enviando a Telegram: {e}")


if __name__ == "__main__":
    check_nitter()

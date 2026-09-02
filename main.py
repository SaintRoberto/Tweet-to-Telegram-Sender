from pathlib import Path

src = Path("/mnt/data/main.py")
dst = Path("/mnt/data/main_corregido.py")

# Reuse the code string from this execution by reconstructing from the read-only mounted main.py is not possible,
# so write the corrected version to a new writable filename.
code = '''import requests
import os
import re
import json
import time
import html
import unicodedata
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1
GEO_CACHE_FILE = "geo_cache.json"
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "BotMonitoreoEcuador/2.0 (https://github.com/SaintRoberto/Tweet-to-Telegram-Sender)"
)

ultima_consulta_nominatim = 0.0


def cargar_lista(archivo):
    if not os.path.exists(archivo):
        return []
    with open(archivo, "r", encoding="utf-8") as f:
        return [
            line.strip().lower()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]


def cargar_fuentes(archivo="fuentes_rss.txt"):
    if not os.path.exists(archivo):
        return []
    with open(archivo, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]


def limpiar_html(texto):
    texto = html.unescape(texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"https?://\\S+", " ", texto)
    texto = re.sub(r"\\s+", " ", texto)
    return texto.strip()


def normalizar_texto(texto):
    texto = limpiar_html(texto).lower()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def es_relevante(texto, palabras_clave):
    texto_normalizado = normalizar_texto(texto)
    return any(
        normalizar_texto(p) in texto_normalizado
        for p in palabras_clave
        if normalizar_texto(p)
    )


def esta_excluido(texto, frases_exclusion):
    texto_normalizado = normalizar_texto(texto)
    return any(
        normalizar_texto(f) in texto_normalizado
        for f in frases_exclusion
        if normalizar_texto(f)
    )


def cargar_geo_cache():
    if not os.path.exists(GEO_CACHE_FILE):
        return {}
    try:
        with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def guardar_geo_cache(cache):
    try:
        with open(GEO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando {GEO_CACHE_FILE}: {e}")


GEO_CACHE = cargar_geo_cache()


def limpiar_candidato_ubicacion(candidato):
    candidato = limpiar_html(candidato)
    candidato = re.split(
        r"\\b(?:deja|dejó|dejan|dejando|provoca|provocó|provocan|provocando|"
        r"causa|causó|causan|causando|afecta|afectó|afectan|afectando|"
        r"reporta|reportó|reportan|registra|registró|registran|"
        r"decide|decidió|decidieron|ocurre|ocurrió|sucede|sucedió|"
        r"tras|donde|mientras)\\b",
        candidato,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]
    candidato = candidato.strip(" ,;:-–—()[]{}")
    partes = [p.strip() for p in candidato.split(",") if p.strip()]
    if len(partes) >= 2:
        candidato = ", ".join(partes[:2])
    palabras = candidato.split()
    if len(palabras) > 10:
        candidato = " ".join(palabras[:10])
    return candidato.strip()


def extraer_candidatos_ubicacion(texto):
    texto = limpiar_html(texto)
    candidatos = []

    patrones = [
        r"\\b(?:en|desde|hacia|cerca de|frente a|al norte de|al sur de|al este de|al oeste de)\\s+([^.!?;\\n]{2,120})",
        r"\\b(?:provincia|cant[oó]n|parroquia|sector|barrio|comunidad|recinto|ciudad|localidad)\\s+(?:de\\s+)?([^.!?;\\n]{2,120})",
        r"\\b(?:avenida|av\\.?|calle|v[ií]a)\\s+([^.!?;\\n]{2,120})",
    ]

    for patron in patrones:
        for match in re.finditer(patron, texto, flags=re.IGNORECASE):
            candidato = limpiar_candidato_ubicacion(match.group(1))
            if len(candidato) < 3:
                continue
            candidatos.append(candidato)
            partes = [p.strip() for p in candidato.split(",") if p.strip()]
            if len(partes) >= 2:
                candidatos.append(", ".join(partes[:2]))
                candidatos.extend(partes[:2])
            elif partes:
                candidatos.append(partes[0])

    hashtags_genericos = {
        "urgente", "atencion", "alerta", "sismo", "terremoto",
        "lluvias", "lluvia", "inundacion", "inundaciones",
        "incendio", "incendios", "deslizamiento", "emergencia",
        "noticias", "ecuador"
    }

    for hashtag in re.findall(r"#([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_-]{3,40})", texto):
        etiqueta = hashtag.replace("_", " ").replace("-", " ").strip()
        clave = normalizar_texto(etiqueta)
        if clave and clave not in hashtags_genericos:
            candidatos.append(etiqueta)

    resultado = []
    vistos = set()
    for candidato in candidatos:
        clave = normalizar_texto(candidato)
        if len(clave) < 3 or clave in vistos:
            continue
        vistos.add(clave)
        resultado.append(candidato)

    return resultado[:12]


def consultar_nominatim(ubicacion):
    global ultima_consulta_nominatim

    clave = normalizar_texto(ubicacion)
    if not clave:
        return None

    if clave in GEO_CACHE:
        return GEO_CACHE[clave]

    transcurrido = time.time() - ultima_consulta_nominatim
    if transcurrido < NOMINATIM_DELAY:
        time.sleep(NOMINATIM_DELAY - transcurrido)

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": ubicacion,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 5,
                "accept-language": "es",
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=12
        )

        ultima_consulta_nominatim = time.time()

        if response.status_code != 200:
            print(f"Nominatim HTTP {response.status_code} para '{ubicacion}'")
            return None

        resultados = response.json()
        if not resultados:
            info = {"country_code": None, "display_name": None}
            GEO_CACHE[clave] = info
            guardar_geo_cache(GEO_CACHE)
            return info

        primero = resultados[0]
        direccion = primero.get("address") or {}
        info = {
            "country_code": (direccion.get("country_code") or "").lower() or None,
            "display_name": primero.get("display_name")
        }

        GEO_CACHE[clave] = info
        guardar_geo_cache(GEO_CACHE)
        return info

    except requests.RequestException as e:
        print(f"Error consultando Nominatim para '{ubicacion}': {e}")
        return None
    except Exception as e:
        print(f"Error geográfico para '{ubicacion}': {e}")
        return None


def impacto_hacia_ecuador(texto):
    texto = normalizar_texto(texto)
    patrones = [
        (
            r"\\b(?:afectara|afectaria|afecta|afectando|impactara|impactaria|impacta|"
            r"llegara|llegaria|llega|se sentira|se sentiria|amenaza|amenazaria)\\b"
            r".{0,160}\\becuador\\b"
        ),
        (
            r"\\becuador\\b.{0,160}"
            r"\\b(?:afectad|impact|amenaz|alerta|oleaje|ceniza|se sentira|llegara)\\w*"
        ),
    ]
    return any(re.search(p, texto) for p in patrones)


def esta_relacionado_con_ecuador(texto_tuit):
    texto_limpio = limpiar_html(texto_tuit)
    texto_normalizado = normalizar_texto(texto_limpio)
    candidatos = extraer_candidatos_ubicacion(texto_limpio)

    print(
        "Ubicaciones detectadas: "
        + (" | ".join(candidatos) if candidatos else "(ninguna)")
    )

    encontro_ecuador = False
    encontro_extranjero = False
    ubicaciones_extranjeras = []

    for ubicacion in candidatos:
        info = consultar_nominatim(ubicacion)
        if not info:
            continue

        country_code = (info.get("country_code") or "").lower()
        display_name = info.get("display_name") or ubicacion

        if country_code == "ec":
            encontro_ecuador = True
            print(f"ECUADOR: '{ubicacion}' -> {display_name}")
        elif country_code:
            encontro_extranjero = True
            ubicaciones_extranjeras.append(display_name)
            print(f"EXTRANJERO: '{ubicacion}' -> {display_name}")

    if impacto_hacia_ecuador(texto_limpio):
        print("ACEPTADO: evento extranjero con impacto explícito sobre Ecuador.")
        return True

    if encontro_extranjero:
        print("DESCARTADO: se detectó ubicación extranjera.")
        for lugar in ubicaciones_extranjeras:
            print(f"  -> {lugar}")
        return False

    if encontro_ecuador:
        print("ACEPTADO: ubicación confirmada en Ecuador.")
        return True

    if re.search(r"\\becuador\\b", texto_normalizado):
        print("ACEPTADO: Ecuador aparece explícitamente en el texto del tuit.")
        return True

    print("DESCARTADO: no se pudo confirmar que el evento ocurrió en Ecuador.")
    return False


def extraer_tweet_id(link):
    match = re.search(r"/status/(\\d+)", link)
    return match.group(1) if match else None


def marcar_procesado(tweet_id, enviados, nuevos_ids):
    enviados.add(tweet_id)
    nuevos_ids.append(tweet_id)


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
    print("Filtro geográfico Ecuador v2: ACTIVADO")

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
                print(f"Fuente inválida en fuentes_rss.txt (falta {{usuario}}): {plantilla_url}")
                continue

            url = plantilla_url.replace("{usuario}", usuario)

            try:
                response = requests.get(url, headers=headers, timeout=10)

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
                print(f"Fuente OK para @{usuario}: {len(items)} publicaciones encontradas")

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
                        if description_element is not None and description_element.text
                        else ""
                    )

                    link = link_element.text or ""
                    tweet_id = extraer_tweet_id(link)

                    if not tweet_id:
                        print(f"No se pudo extraer tweet ID de: {link}")
                        continue

                    if tweet_id in enviados:
                        continue

                    # Exclusiones y palabras clave usan title + description.
                    texto_publicacion = f"{title} {description}"

                    if esta_excluido(texto_publicacion, frases_exclusion):
                        print(f"EXCLUIDO @{usuario}: {title or description}")
                        marcar_procesado(tweet_id, enviados, nuevos_ids)
                        continue

                    if not es_relevante(texto_publicacion, palabras):
                        print(f"NO RELEVANTE @{usuario}: {title or description}")
                        marcar_procesado(tweet_id, enviados, nuevos_ids)
                        continue

                    # GEOGRAFÍA: SOLO el texto real del tuit.
                    # Así el nombre de la cuenta no mete falsamente "Ecuador".
                    if not esta_relacionado_con_ecuador(title):
                        print(f"FUERA DE ECUADOR @{usuario}: {title or description}")
                        marcar_procesado(tweet_id, enviados, nuevos_ids)
                        continue

                    link_x = f"https://x.com/{usuario}/status/{tweet_id}"
                    send_telegram(link_x)
                    marcar_procesado(tweet_id, enviados, nuevos_ids)

                exito_usuario = True

            except requests.RequestException as e:
                print(f"Error HTTP con @{usuario} en {url}: {e}")
                continue
            except Exception as e:
                print(f"Error con @{usuario} en {url}: {e}")
                continue

        if not exito_usuario:
            print(f"No se encontró una fuente RSS funcional para @{usuario}")

    with open("last_id.txt", "w", encoding="utf-8") as f:
        f.write("\\n".join(nuevos_ids[-200:]))


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print("Error: faltan TELEGRAM_TOKEN o TELEGRAM_TO en las variables de entorno.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={"chat_id": CHAT_ID, "text": text},
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
'''

dst.write_text(code, encoding="utf-8")
compile(code, str(dst), "exec")
print(f"Archivo corregido y validado: {dst}")

import requests
import os
import re
import json
import time
import html
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1
GEO_CACHE_FILE = "geo_cache.json"
HISTORY_FILE = Path("last_id.txt")

# Hay 194 cuentas y se leen hasta 3 publicaciones por cuenta. El límite
# anterior de 200 IDs no alcanzaba ni para conservar un escaneo completo:
# los IDs olvidados volvían a Telegram en la siguiente ejecución.
MAX_HISTORY_IDS = int(os.getenv("MAX_HISTORY_IDS", "20000"))
MAX_TWEET_AGE_HOURS = int(os.getenv("MAX_TWEET_AGE_HOURS", "24"))
TWITTER_EPOCH_MS = 1288834974657

NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "BotMonitoreoEcuador/2.1 "
    "(https://github.com/SaintRoberto/Tweet-to-Telegram-Sender)"
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
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def normalizar_texto(texto):
    texto = limpiar_html(texto).lower()
    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        c
        for c in texto
        if unicodedata.category(c) != "Mn"
    )

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


def normalizar_para_filtro(texto):
    texto = normalizar_texto(texto)

    reemplazos = {
        "4": "a",
        "@": "a",
        "3": "e",
        "1": "i",
        "!": "i",
        "0": "o",
        "5": "s",
        "$": "s",
        "7": "t",
    }

    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)

    return re.sub(
        r"\s+",
        " ",
        texto
    ).strip()


def es_relevante(texto, palabras_clave):
    texto_normalizado = normalizar_para_filtro(
        texto
    )

    for palabra in palabras_clave:
        palabra_normalizada = normalizar_para_filtro(
            palabra
        )

        if (
            palabra_normalizada
            and palabra_normalizada in texto_normalizado
        ):
            return True

    return False


def esta_excluido(texto, frases_exclusion):
    texto_normalizado = normalizar_para_filtro(
        texto
    )

    for frase in frases_exclusion:
        frase_normalizada = normalizar_para_filtro(
            frase
        )

        if (
            frase_normalizada
            and frase_normalizada in texto_normalizado
        ):
            return True

    return False


def cargar_geo_cache():
    if not os.path.exists(
        GEO_CACHE_FILE
    ):
        return {}

    try:
        with open(
            GEO_CACHE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

            if isinstance(
                data,
                dict
            ):
                return data

    except Exception:
        pass

    return {}


def guardar_geo_cache(cache):
    try:
        with open(
            GEO_CACHE_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                cache,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print(
            f"Error guardando "
            f"{GEO_CACHE_FILE}: {e}"
        )


GEO_CACHE = cargar_geo_cache()


def limpiar_candidato_ubicacion(candidato):
    candidato = limpiar_html(
        candidato
    )

    candidato = re.split(
        r"\b(?:"
        r"deja|dejo|dejó|dejan|dejando|"
        r"provoca|provoco|provocó|provocan|provocando|"
        r"causa|causo|causó|causan|causando|"
        r"afecta|afecto|afectó|afectan|afectando|"
        r"reporta|reporto|reportó|reportan|"
        r"registra|registro|registró|registran|"
        r"decide|decidio|decidió|decidieron|"
        r"ocurre|ocurrio|ocurrió|"
        r"sucede|sucedio|sucedió|"
        r"tras|donde|mientras"
        r")\b",
        candidato,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    candidato = candidato.strip(
        " ,;:-–—()[]{}"
    )

    partes = [
        p.strip()
        for p in candidato.split(",")
        if p.strip()
    ]

    if len(partes) >= 2:
        candidato = ", ".join(
            partes[:2]
        )

    palabras = candidato.split()

    if len(palabras) > 10:
        candidato = " ".join(
            palabras[:10]
        )

    return candidato.strip()


def parece_fragmento_geografico(fragmento):
    fragmento = limpiar_html(
        fragmento
    ).strip()

    if not fragmento:
        return False

    palabras = fragmento.split()

    if not (
        1 <= len(palabras) <= 5
    ):
        return False

    if not re.search(
        r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]",
        fragmento
    ):
        return False

    return True


def extraer_candidatos_ubicacion(texto):
    texto = limpiar_html(texto)

    candidatos = []

    patrones = [
        (
            r"\b(?:"
            r"en|desde|hacia|"
            r"cerca de|frente a|"
            r"al norte de|"
            r"al sur de|"
            r"al este de|"
            r"al oeste de"
            r")\s+"
            r"([^.!?;\n]{2,100})"
        ),

        (
            r"\b(?:"
            r"provincia|"
            r"cant[oó]n|"
            r"parroquia|"
            r"sector|"
            r"barrio|"
            r"comunidad|"
            r"recinto|"
            r"ciudad|"
            r"localidad"
            r")\s+"
            r"(?:de\s+)?"
            r"([^.!?;\n]{2,100})"
        ),

        (
            r"\b(?:"
            r"avenida|"
            r"av\.?|"
            r"calle|"
            r"v[ií]a"
            r")\s+"
            r"([^.!?;\n]{2,100})"
        ),
    ]

    for patron in patrones:
        for match in re.finditer(
            patron,
            texto,
            flags=re.IGNORECASE
        ):
            candidato = limpiar_candidato_ubicacion(
                match.group(1)
            )

            if len(candidato) < 3:
                continue

            candidatos.append(
                candidato
            )

            partes = [
                p.strip()
                for p in candidato.split(",")
                if p.strip()
            ]

            if len(partes) >= 2:
                candidatos.append(
                    ", ".join(
                        partes[:2]
                    )
                )

                candidatos.append(
                    partes[0]
                )

                candidatos.append(
                    partes[1]
                )

            elif partes:
                candidatos.append(
                    partes[0]
                )

    fragmentos = re.split(
        r"[,;|]",
        texto
    )

    for fragmento in fragmentos:
        fragmento = fragmento.strip(
            " .:-–—"
        )

        if parece_fragmento_geografico(
            fragmento
        ):
            candidatos.append(
                fragmento
            )

    hashtags_genericos = {
        "urgente",
        "atencion",
        "alerta",
        "sismo",
        "terremoto",
        "lluvias",
        "lluvia",
        "inundacion",
        "inundaciones",
        "incendio",
        "incendios",
        "deslizamiento",
        "emergencia",
        "noticias",
        "ecuador",
    }

    hashtags = re.findall(
        r"#([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_-]{3,40})",
        texto
    )

    for hashtag in hashtags:
        etiqueta = (
            hashtag
            .replace("_", " ")
            .replace("-", " ")
            .strip()
        )

        clave = normalizar_texto(
            etiqueta
        )

        if (
            clave
            and clave not in hashtags_genericos
        ):
            candidatos.append(
                etiqueta
            )

    resultado = []
    vistos = set()

    for candidato in candidatos:
        candidato = candidato.strip()

        clave = normalizar_texto(
            candidato
        )

        if len(clave) < 3:
            continue

        if clave in vistos:
            continue

        vistos.add(
            clave
        )

        resultado.append(
            candidato
        )

    return resultado[:15]


def consultar_nominatim(ubicacion):
    global ultima_consulta_nominatim

    clave = normalizar_texto(
        ubicacion
    )

    if not clave:
        return None

    if clave in GEO_CACHE:
        return GEO_CACHE[
            clave
        ]

    transcurrido = (
        time.time()
        - ultima_consulta_nominatim
    )

    if transcurrido < NOMINATIM_DELAY:
        time.sleep(
            NOMINATIM_DELAY
            - transcurrido
        )

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
            headers={
                "User-Agent":
                    NOMINATIM_USER_AGENT
            },
            timeout=12
        )

        ultima_consulta_nominatim = (
            time.time()
        )

        if response.status_code != 200:
            print(
                f"Nominatim HTTP "
                f"{response.status_code} "
                f"para '{ubicacion}'"
            )

            return None

        resultados = response.json()

        if not resultados:
            info = {
                "country_code": None,
                "display_name": None
            }

            GEO_CACHE[
                clave
            ] = info

            guardar_geo_cache(
                GEO_CACHE
            )

            return info

        primero = resultados[0]

        direccion = (
            primero.get(
                "address"
            )
            or
            {}
        )

        country_code = (
            direccion.get(
                "country_code"
            )
            or
            ""
        ).lower()

        info = {
            "country_code":
                country_code
                or
                None,

            "display_name":
                primero.get(
                    "display_name"
                )
        }

        GEO_CACHE[
            clave
        ] = info

        guardar_geo_cache(
            GEO_CACHE
        )

        return info

    except requests.RequestException as e:
        print(
            f"Error consultando "
            f"Nominatim para "
            f"'{ubicacion}': {e}"
        )

        return None

    except Exception as e:
        print(
            f"Error geográfico "
            f"para '{ubicacion}': "
            f"{e}"
        )

        return None


def impacto_hacia_ecuador(texto):
    texto = normalizar_texto(
        texto
    )

    patrones = [
        (
            r"\b(?:"
            r"afectara|"
            r"afectaria|"
            r"afecta|"
            r"afectando|"
            r"impactara|"
            r"impactaria|"
            r"impacta|"
            r"llegara|"
            r"llegaria|"
            r"llega|"
            r"se sentira|"
            r"se sentiria|"
            r"amenaza|"
            r"amenazaria"
            r")\b"
            r".{0,160}"
            r"\becuador\b"
        ),

        (
            r"\becuador\b"
            r".{0,160}"
            r"\b(?:"
            r"afectad|"
            r"impact|"
            r"amenaz|"
            r"alerta|"
            r"oleaje|"
            r"ceniza|"
            r"se sentira|"
            r"llegara"
            r")\w*"
        ),
    ]

    return any(
        re.search(
            patron,
            texto
        )
        for patron in patrones
    )


def esta_relacionado_con_ecuador(texto_tuit):
    texto_limpio = limpiar_html(
        texto_tuit
    )

    texto_normalizado = normalizar_texto(
        texto_limpio
    )

    candidatos = extraer_candidatos_ubicacion(
        texto_limpio
    )

    print(
        "Ubicaciones detectadas: "
        +
        (
            " | ".join(
                candidatos
            )
            if candidatos
            else "(ninguna)"
        )
    )

    encontro_ecuador = False
    encontro_extranjero = False

    ubicaciones_extranjeras = []

    for ubicacion in candidatos:
        info = consultar_nominatim(
            ubicacion
        )

        if not info:
            continue

        country_code = (
            info.get(
                "country_code"
            )
            or
            ""
        ).lower()

        display_name = (
            info.get(
                "display_name"
            )
            or
            ubicacion
        )

        if country_code == "ec":
            encontro_ecuador = True

            print(
                f"ECUADOR: "
                f"'{ubicacion}' -> "
                f"{display_name}"
            )

        elif country_code:
            encontro_extranjero = True

            ubicaciones_extranjeras.append(
                display_name
            )

            print(
                f"EXTRANJERO: "
                f"'{ubicacion}' -> "
                f"{display_name}"
            )

    if impacto_hacia_ecuador(
        texto_limpio
    ):
        print(
            "ACEPTADO: evento extranjero "
            "con afectación explícita "
            "sobre Ecuador."
        )

        return True

    if encontro_extranjero:
        print(
            "DESCARTADO: se detectó "
            "ubicación extranjera."
        )

        for lugar in ubicaciones_extranjeras:
            print(
                f"  -> {lugar}"
            )

        return False

    if encontro_ecuador:
        print(
            "ACEPTADO: ubicación "
            "confirmada en Ecuador."
        )

        return True

    if re.search(
        r"\becuador\b",
        texto_normalizado
    ):
        print(
            "ACEPTADO: Ecuador aparece "
            "explícitamente en el texto "
            "del tuit."
        )

        return True

    print(
        "DESCARTADO: no se pudo "
        "confirmar que el evento "
        "ocurrió en Ecuador."
    )

    return False


def extraer_tweet_id(link):
    match = re.search(
        r"/status/(\d+)",
        link
    )

    return (
        match.group(1)
        if match
        else None
    )


def fecha_tweet_desde_id(tweet_id):
    try:
        timestamp_ms = (int(tweet_id) >> 22) + TWITTER_EPOCH_MS
        return datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def es_tweet_antiguo(tweet_id, ahora=None):
    fecha_tweet = fecha_tweet_desde_id(tweet_id)

    if fecha_tweet is None:
        return False

    ahora = ahora or datetime.now(timezone.utc)
    return ahora - fecha_tweet > timedelta(hours=MAX_TWEET_AGE_HOURS)


def cargar_historial(archivo=HISTORY_FILE):
    archivo = Path(archivo)

    if not archivo.exists():
        return []

    historial = []
    vistos = set()

    with archivo.open("r", encoding="utf-8") as f:
        for line in f:
            tweet_id = line.strip()

            if not tweet_id or tweet_id in vistos:
                continue

            vistos.add(tweet_id)
            historial.append(tweet_id)

    return historial


def guardar_historial(historial, archivo=HISTORY_FILE):
    archivo = Path(archivo)
    historial = historial[-MAX_HISTORY_IDS:]
    temporal = archivo.with_suffix(archivo.suffix + ".tmp")

    temporal.write_text(
        "\n".join(historial) + ("\n" if historial else ""),
        encoding="utf-8"
    )

    # Reemplazo atómico: nunca deja last_id.txt incompleto si el proceso falla.
    os.replace(temporal, archivo)


def marcar_procesado(
    tweet_id,
    enviados,
    nuevos_ids
):
    if tweet_id in enviados:
        return

    enviados.add(
        tweet_id
    )

    nuevos_ids.append(
        tweet_id
    )


def check_nitter():
    cuentas = cargar_lista(
        "cuentas.txt"
    )

    palabras = cargar_lista(
        "palabras.txt"
    )

    frases_exclusion = cargar_lista(
        "frases_exclusion.txt"
    )

    fuentes = cargar_fuentes()

    if not cuentas or not palabras:
        print(
            "Error: cuentas.txt "
            "o palabras.txt "
            "están vacíos."
        )

        return

    if not fuentes:
        print(
            "Error: fuentes_rss.txt "
            "está vacío o no existe."
        )

        return

    historial_ids = cargar_historial()

    enviados = set(
        historial_ids
    )

    nuevos_ids = list(
        historial_ids
    )

    print(
        f"Iniciando escaneo de "
        f"{len(cuentas)} cuentas..."
    )

    print(
        f"Fuentes RSS cargadas: "
        f"{len(fuentes)}"
    )

    print(
        f"Palabras clave cargadas: "
        f"{len(palabras)}"
    )

    print(
        f"Frases de exclusión cargadas: "
        f"{len(frases_exclusion)}"
    )

    print(
        "Filtro geográfico Ecuador: ACTIVADO"
    )

    print(
        "Normalización anti-leetspeak: ACTIVADA"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; "
            "Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/152.0.0.0 "
            "Safari/537.36"
        )
    }

    for usuario in cuentas:
        exito_usuario = False

        for plantilla_url in fuentes:
            if exito_usuario:
                break

            if "{usuario}" not in plantilla_url:
                print(
                    "Fuente inválida "
                    "en fuentes_rss.txt "
                    "(falta {usuario}): "
                    f"{plantilla_url}"
                )

                continue

            url = (
                plantilla_url
                .replace(
                    "{usuario}",
                    usuario
                )
            )

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=10
                )

                print(
                    f"@{usuario} -> "
                    f"{url}: "
                    f"HTTP "
                    f"{response.status_code} "
                    f"("
                    f"{len(response.content)} "
                    f"bytes)"
                )

                if (
                    response.status_code
                    !=
                    200
                ):
                    continue

                if (
                    len(
                        response.content
                    )
                    <=
                    100
                ):
                    print(
                        "Respuesta demasiado "
                        f"corta: {url}"
                    )

                    continue

                try:
                    root = ET.fromstring(
                        response.content
                    )

                except ET.ParseError as e:
                    print(
                        f"No es XML/RSS "
                        f"válido en {url}: "
                        f"{e}"
                    )

                    continue

                items = root.findall(
                    ".//item"
                )

                if not items:
                    print(
                        f"Sin items RSS "
                        f"en {url}"
                    )

                    continue

                items = items[:3]

                print(
                    f"Fuente OK para "
                    f"@{usuario}: "
                    f"{len(items)} "
                    f"publicaciones encontradas"
                )

                for item in items:
                    title_element = (
                        item.find(
                            "title"
                        )
                    )

                    link_element = (
                        item.find(
                            "link"
                        )
                    )

                    description_element = (
                        item.find(
                            "description"
                        )
                    )

                    if (
                        link_element
                        is None
                    ):
                        continue

                    title = (
                        title_element.text
                        if
                        title_element is not None
                        and
                        title_element.text
                        else
                        ""
                    )

                    description = (
                        description_element.text
                        if
                        description_element
                        is not None
                        and
                        description_element.text
                        else
                        ""
                    )

                    link = (
                        link_element.text
                        or
                        ""
                    )

                    tweet_id = (
                        extraer_tweet_id(
                            link
                        )
                    )

                    if not tweet_id:
                        print(
                            "No se pudo "
                            "extraer tweet ID "
                            f"de: {link}"
                        )

                        continue

                    if (
                        tweet_id
                        in enviados
                    ):
                        continue

                    # Un tuit viejo nunca debe reaparecer como alerta nueva,
                    # incluso si una ejecución anterior no guardó su ID.
                    if es_tweet_antiguo(tweet_id):
                        print(
                            f"ANTIGUO @{usuario}: {tweet_id} "
                            f"(más de {MAX_TWEET_AGE_HOURS} horas)"
                        )

                        marcar_procesado(
                            tweet_id,
                            enviados,
                            nuevos_ids
                        )

                        continue

                    texto_publicacion = (
                        f"{title} "
                        f"{description}"
                    )

                    # 1. EXCLUSIONES
                    if esta_excluido(
                        texto_publicacion,
                        frases_exclusion
                    ):
                        print(
                            f"EXCLUIDO "
                            f"@{usuario}: "
                            f"{title or description}"
                        )

                        marcar_procesado(
                            tweet_id,
                            enviados,
                            nuevos_ids
                        )

                        continue

                    # 2. PALABRAS CLAVE
                    if not es_relevante(
                        texto_publicacion,
                        palabras
                    ):
                        print(
                            f"NO RELEVANTE "
                            f"@{usuario}: "
                            f"{title or description}"
                        )

                        marcar_procesado(
                            tweet_id,
                            enviados,
                            nuevos_ids
                        )

                        continue

                    # 3. GEOGRAFÍA:
                    # SOLO EL TEXTO REAL DEL TUIT
                    if not esta_relacionado_con_ecuador(
                        title
                    ):
                        print(
                            f"FUERA DE ECUADOR "
                            f"@{usuario}: "
                            f"{title or description}"
                        )

                        marcar_procesado(
                            tweet_id,
                            enviados,
                            nuevos_ids
                        )

                        continue

                    # 4. ENVIAR
                    link_x = (
                        f"https://x.com/"
                        f"{usuario}/status/"
                        f"{tweet_id}"
                    )

                    print(
                        f"ENVIANDO "
                        f"@{usuario}: "
                        f"{link_x}"
                    )

                    enviado_correctamente = send_telegram(link_x)

                    if not enviado_correctamente:
                        print(
                            f"NO REGISTRADO @{usuario}: Telegram no "
                            "confirmó el envío; se reintentará después."
                        )
                        continue

                    marcar_procesado(
                        tweet_id,
                        enviados,
                        nuevos_ids
                    )

                    # Persistir inmediatamente después de un envío exitoso.
                    # Así, si el proceso falla más adelante, este ID no se pierde.
                    guardar_historial(nuevos_ids)

                exito_usuario = True

            except requests.RequestException as e:
                print(
                    f"Error HTTP con "
                    f"@{usuario} "
                    f"en {url}: {e}"
                )

                continue

            except Exception as e:
                print(
                    f"Error con "
                    f"@{usuario} "
                    f"en {url}: {e}"
                )

                continue

        if not exito_usuario:
            print(
                "No se encontró "
                "una fuente RSS "
                "funcional para "
                f"@{usuario}"
            )

    guardar_historial(nuevos_ids)

    print(
        f"Memoria actualizada: {min(len(nuevos_ids), MAX_HISTORY_IDS)} "
        f"IDs conservados (máximo {MAX_HISTORY_IDS})."
    )


def send_telegram(text):
    if (
        not TOKEN
        or
        not CHAT_ID
    ):
        print(
            "Error: faltan "
            "TELEGRAM_TOKEN "
            "o TELEGRAM_TO "
            "en las variables "
            "de entorno."
        )

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            json={
                "chat_id":
                    CHAT_ID,

                "text":
                    text
            },
            timeout=10
        )

        if (
            response.status_code
            !=
            200
        ):
            print(
                "Error enviando "
                "a Telegram: "
                f"HTTP "
                f"{response.status_code} "
                f"- "
                f"{response.text[:200]}"
            )

            return False

        return True

    except requests.RequestException as e:
        print(
            f"Error enviando "
            f"a Telegram: {e}"
        )

        return False


if __name__ == "__main__":
    check_nitter()

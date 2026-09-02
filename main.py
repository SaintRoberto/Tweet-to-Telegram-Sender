import requests
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
    "BotMonitoreoEcuador/1.0 "
    "(https://github.com/SaintRoberto/Tweet-to-Telegram-Sender)"
)

ultima_consulta_nominatim = 0.0


def cargar_lista(archivo):
    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f:
            return [
                line.strip().lower()
                for line in f
                if line.strip()
                and not line.lstrip().startswith("#")
            ]

    return []


def cargar_fuentes(archivo="fuentes_rss.txt"):
    if not os.path.exists(archivo):
        return []

    with open(archivo, "r", encoding="utf-8") as f:
        return [
            line.strip()
            for line in f
            if line.strip()
            and not line.lstrip().startswith("#")
        ]


def limpiar_html(texto):
    texto = html.unescape(texto or "")

    texto = re.sub(
        r"<[^>]+>",
        " ",
        texto
    )

    texto = re.sub(
        r"https?://\S+",
        " ",
        texto
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def normalizar_texto(texto):
    texto = limpiar_html(
        texto
    ).lower()

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    return "".join(
        caracter
        for caracter in texto
        if unicodedata.category(
            caracter
        ) != "Mn"
    )


def es_relevante(
    texto,
    palabras_clave
):
    texto = texto.lower()

    return any(
        palabra in texto
        for palabra in palabras_clave
    )


def esta_excluido(
    texto,
    frases_exclusion
):
    texto = texto.lower()

    return any(
        frase in texto
        for frase in frases_exclusion
    )


# =========================================================
# CACHE GEOGRÁFICO
# =========================================================

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

            data = json.load(
                f
            )

            if isinstance(
                data,
                dict
            ):
                return data

    except Exception:
        pass

    return {}


def guardar_geo_cache(
    cache
):
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


# =========================================================
# EXTRAER POSIBLES UBICACIONES DEL TUIT
# =========================================================

def limpiar_candidato_ubicacion(
    candidato
):
    candidato = limpiar_html(
        candidato
    )

    candidato = re.split(
        r"\b(?:"
        r"deja|dejó|dejan|dejando|"
        r"provoca|provocó|provocan|provocando|"
        r"causa|causó|causan|causando|"
        r"afecta|afectó|afectan|afectando|"
        r"reporta|reportó|reportan|"
        r"registra|registró|registran|"
        r"tras|donde|mientras|"
        r"podría sentirse|podria sentirse|"
        r"podría afectar|podria afectar|"
        r"podría llegar|podria llegar"
        r")\b",
        candidato,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    candidato = candidato.strip(
        " ,;:-–—()[]{}"
    )

    palabras = candidato.split()

    if len(palabras) > 12:
        candidato = " ".join(
            palabras[:12]
        )

    return candidato


def variantes_candidato(
    candidato
):
    candidato = (
        limpiar_candidato_ubicacion(
            candidato
        )
    )

    if len(candidato) < 3:
        return []

    variantes = [
        candidato
    ]

    partes = [
        parte.strip()
        for parte in candidato.split(",")
        if parte.strip()
    ]

    if len(partes) >= 3:
        variantes.append(
            ", ".join(
                partes[:3]
            )
        )

    if len(partes) >= 2:
        variantes.append(
            ", ".join(
                partes[:2]
            )
        )

    if partes:
        variantes.append(
            partes[0]
        )

    sin_prefijo = re.sub(
        r"^(?:"
        r"la|el|los|las|"
        r"sector|barrio|"
        r"parroquia|cant[oó]n|"
        r"provincia|comunidad|"
        r"recinto|ciudad|localidad|"
        r"v[ií]a|avenida|av\.?|calle"
        r")\s+(?:de\s+)?",
        "",
        candidato,
        flags=re.IGNORECASE
    ).strip()

    if (
        sin_prefijo
        and
        sin_prefijo != candidato
    ):
        variantes.append(
            sin_prefijo
        )

    resultado = []
    vistos = set()

    for item in variantes:

        clave = normalizar_texto(
            item
        )

        if (
            clave
            and
            clave not in vistos
        ):
            vistos.add(
                clave
            )

            resultado.append(
                item
            )

    return resultado


def extraer_candidatos_ubicacion(
    texto
):
    texto = limpiar_html(
        texto
    )

    candidatos = []

    # Si aparece Ecuador directamente.
    if re.search(
        r"\bEcuador\b",
        texto,
        flags=re.IGNORECASE
    ):
        candidatos.append(
            "Ecuador"
        )

    patrones = [

        # "en Quito"
        # "en Zúrich, Suiza"
        # "cerca de Cuenca"
        (
            r"\b(?:"
            r"en|desde|hacia|"
            r"cerca de|frente a|"
            r"al norte de|"
            r"al sur de|"
            r"al este de|"
            r"al oeste de"
            r")\s+"
            r"([^.!?;\n]{2,120})"
        ),

        # "parroquia Sayausí"
        # "sector Mapasingue"
        # "cantón Durán"
        (
            r"\b(?:"
            r"provincia|cant[oó]n|"
            r"parroquia|sector|"
            r"barrio|comunidad|"
            r"recinto|ciudad|localidad"
            r")\s+"
            r"(?:de\s+)?"
            r"([^.!?;\n]{2,120})"
        ),

        # "Av. 9 de Octubre"
        # "calle ..."
        # "vía Quito-Papallacta"
        (
            r"\b(?:"
            r"avenida|av\.?|"
            r"calle|v[ií]a"
            r")\s+"
            r"([^.!?;\n]{2,120})"
        ),
    ]

    for patron in patrones:

        coincidencias = re.finditer(
            patron,
            texto,
            flags=re.IGNORECASE
        )

        for match in coincidencias:

            variantes = (
                variantes_candidato(
                    match.group(1)
                )
            )

            candidatos.extend(
                variantes
            )

    # También intenta usar hashtags
    # como #Quito o #Guayaquil.
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
    }

    hashtags = re.findall(
        r"#("
        r"[A-Za-zÁÉÍÓÚÜÑ"
        r"áéíóúüñ0-9_-]"
        r"{3,40}"
        r")",
        texto
    )

    for hashtag in hashtags:

        etiqueta = (
            hashtag
            .replace(
                "_",
                " "
            )
            .replace(
                "-",
                " "
            )
            .strip()
        )

        clave = normalizar_texto(
            etiqueta
        )

        if (
            clave
            and
            clave not in hashtags_genericos
        ):
            candidatos.append(
                etiqueta
            )

    resultado = []
    vistos = set()

    for candidato in candidatos:

        clave = normalizar_texto(
            candidato
        )

        if (
            clave
            and
            clave not in vistos
        ):
            vistos.add(
                clave
            )

            resultado.append(
                candidato
            )

    # Máximo 10 consultas potenciales.
    return resultado[:10]


# =========================================================
# CONSULTA OPENSTREETMAP / NOMINATIM
# =========================================================

def consultar_nominatim(
    ubicacion
):
    global ultima_consulta_nominatim

    clave = normalizar_texto(
        ubicacion
    )

    if not clave:
        return None

    # Ya consultado anteriormente.
    if clave in GEO_CACHE:
        return GEO_CACHE[
            clave
        ]

    # No bombardear Nominatim.
    transcurrido = (
        time.time()
        -
        ultima_consulta_nominatim
    )

    if (
        transcurrido
        <
        NOMINATIM_DELAY
    ):
        time.sleep(
            NOMINATIM_DELAY
            -
            transcurrido
        )

    try:

        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": ubicacion,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 3,
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

        if (
            response.status_code
            !=
            200
        ):
            print(
                f"Nominatim HTTP "
                f"{response.status_code} "
                f"para '{ubicacion}'"
            )

            return None

        resultados = (
            response.json()
        )

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


# =========================================================
# EVENTOS EXTRANJEROS QUE AFECTAN ECUADOR
# =========================================================

def impacto_hacia_ecuador(
    texto
):
    texto = normalizar_texto(
        texto
    )

    patrones = [

        # "podría afectar Ecuador"
        # "llegará a Ecuador"
        # "se sentirá en Ecuador"
        (
            r"\b(?:"
            r"afectara|afectaria|"
            r"afecta|afectando|"
            r"impactara|impactaria|"
            r"impacta|"
            r"llegara|llegaria|llega|"
            r"se sentira|se sentiria|"
            r"amenaza|amenazaria"
            r")\b"
            r".{0,140}"
            r"\becuador\b"
        ),

        # "Ecuador podría verse afectado..."
        (
            r"\becuador\b"
            r".{0,140}"
            r"\b(?:"
            r"afectad|impact|"
            r"amenaz|alerta|"
            r"oleaje|ceniza|"
            r"se sentira|llegara"
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


# =========================================================
# DECIDIR SI LA NOTICIA ES ECUADOR
# =========================================================

def esta_relacionado_con_ecuador(
    texto
):

    texto_limpio = limpiar_html(
        texto
    )

    texto_normalizado = (
        normalizar_texto(
            texto_limpio
        )
    )

    candidatos = (
        extraer_candidatos_ubicacion(
            texto_limpio
        )
    )

    print(
        "Ubicaciones detectadas: "
        +
        (
            ", ".join(
                candidatos
            )
            if candidatos
            else "(ninguna)"
        )
    )

    encontro_extranjero = False

    for ubicacion in candidatos:

        info = consultar_nominatim(
            ubicacion
        )

        if not info:
            continue

        country_code = info.get(
            "country_code"
        )

        display_name = info.get(
            "display_name"
        )

        # ECUADOR
        if country_code == "ec":

            print(
                f"ECUADOR: "
                f"'{ubicacion}' -> "
                f"{display_name}"
            )

            return True

        # OTRO PAÍS
        if country_code:

            encontro_extranjero = True

            print(
                f"EXTRANJERO: "
                f"'{ubicacion}' -> "
                f"{display_name}"
            )

    # Puede ocurrir fuera pero afectar Ecuador.
    if impacto_hacia_ecuador(
        texto_limpio
    ):

        print(
            "Evento extranjero "
            "con impacto explícito "
            "sobre Ecuador."
        )

        return True

    # Si simplemente dice Ecuador,
    # pero detectamos claramente que
    # el evento sucede fuera, rechazamos.
    if "ecuador" in texto_normalizado:

        if encontro_extranjero:

            print(
                "Se menciona Ecuador, "
                "pero el evento detectado "
                "está fuera del país."
            )

            return False

        print(
            "Ecuador mencionado "
            "sin ubicación extranjera."
        )

        return True

    # MODO ESTRICTO:
    # si no logramos demostrar
    # que está en Ecuador, no se envía.
    print(
        "No se pudo confirmar "
        "una ubicación dentro "
        "de Ecuador."
    )

    return False


def extraer_tweet_id(
    link
):
    match = re.search(
        r"/status/(\d+)",
        link
    )

    return (
        match.group(1)
        if match
        else None
    )


def marcar_procesado(
    tweet_id,
    enviados,
    nuevos_ids
):
    enviados.add(
        tweet_id
    )

    nuevos_ids.append(
        tweet_id
    )


# =========================================================
# ESCANEO RSS
# =========================================================

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

    if (
        not cuentas
        or
        not palabras
    ):
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

    if os.path.exists(
        "last_id.txt"
    ):

        with open(
            "last_id.txt",
            "r",
            encoding="utf-8"
        ) as f:

            historial_ids = [
                line.strip()
                for line in f
                if line.strip()
            ]

    else:
        historial_ids = []

    enviados = set(
        historial_ids
    )

    nuevos_ids = list(
        historial_ids
    )

    print(
        f"Iniciando escaneo "
        f"de {len(cuentas)} "
        f"cuentas..."
    )

    print(
        f"Fuentes RSS cargadas: "
        f"{len(fuentes)}"
    )

    print(
        f"Frases de exclusión "
        f"cargadas: "
        f"{len(frases_exclusion)}"
    )

    print(
        "Filtro geográfico "
        "dinámico para Ecuador: "
        "ACTIVADO"
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

            if (
                "{usuario}"
                not in plantilla_url
            ):

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
                    f"Fuente OK "
                    f"para @{usuario}: "
                    f"{len(items)} "
                    f"publicaciones "
                    f"encontradas"
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
                        title_element
                        is not None
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

                    texto_publicacion = (
                        f"{title} "
                        f"{description}"
                    )

                    # -------------------------
                    # 1. EXCLUSIONES
                    # -------------------------

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

                    # -------------------------
                    # 2. PALABRAS RELEVANTES
                    # -------------------------
                    #
                    # Esto va antes de Nominatim
                    # para no hacer consultas
                    # innecesarias.

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

                    # -------------------------
                    # 3. ECUADOR
                    # -------------------------

                    if not esta_relacionado_con_ecuador(
                        texto_publicacion
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

                    # -------------------------
                    # 4. ENVIAR
                    # -------------------------

                    link_x = (
                        f"https://x.com/"
                        f"{usuario}/status/"
                        f"{tweet_id}"
                    )

                    send_telegram(
                        link_x
                    )

                    marcar_procesado(
                        tweet_id,
                        enviados,
                        nuevos_ids
                    )

                exito_usuario = True

            except requests.RequestException as e:

                print(
                    f"Error HTTP "
                    f"con @{usuario} "
                    f"en {url}: {e}"
                )

                continue

            except Exception as e:

                print(
                    f"Error "
                    f"con @{usuario} "
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

    with open(
        "last_id.txt",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n".join(
                nuevos_ids[-200:]
            )
        )


# =========================================================
# TELEGRAM
# =========================================================

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

        return

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

    except requests.RequestException as e:

        print(
            f"Error enviando "
            f"a Telegram: {e}"
        )


if __name__ == "__main__":
    check_nitter()

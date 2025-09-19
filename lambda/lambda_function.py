import os
import json
import logging
from datetime import datetime, timedelta
import random
import uuid

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_model import Response, DialogState
from ask_sdk_model.dialog import ElicitSlotDirective, DelegateDirective
from ask_sdk_s3.adapter import S3Adapter

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ==============================
# Feature flags & configuración
# ==============================
USE_FAKE_S3 = os.getenv("USE_FAKE_S3", "false").lower() == "true"
ENABLE_DDB_CACHE = os.getenv("ENABLE_DDB_CACHE", "false").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
LIBROS_POR_PAGINA = 10

# ==============================
# Frases naturales y variadas
# ==============================
SALUDOS = [
    "¡Hola! ¡Qué gusto tenerte aquí!",
    "¡Bienvenido de vuelta!",
    "¡Hola! Me alegra que estés aquí.",
    "¡Qué bueno verte por aquí!",
    "¡Hola! Espero que tengas un excelente día."
]

OPCIONES_MENU = [
    "Puedo ayudarte a gestionar tu biblioteca personal. Puedes agregar libros nuevos, ver tu lista de libros, prestar libros a tus amigos, registrar devoluciones o consultar qué libros tienes prestados.",
    "Tengo varias opciones para ti: agregar libros a tu colección, listar todos tus libros, prestar un libro a alguien, devolver un libro que te regresaron, o ver tus préstamos activos.",
    "Puedo hacer varias cosas: agregar libros nuevos a tu biblioteca, mostrarte qué libros tienes, ayudarte a prestar libros, registrar cuando te los devuelven, o decirte qué libros están prestados."
]

PREGUNTAS_QUE_HACER = [
    "¿Qué te gustaría hacer hoy?",
    "¿En qué puedo ayudarte?",
    "¿Qué necesitas?",
    "¿Cómo puedo ayudarte con tu biblioteca?",
    "¿Qué quieres hacer?"
]

ALGO_MAS = [
    "¿Hay algo más en lo que pueda ayudarte?",
    "¿Necesitas algo más?",
    "¿Qué más puedo hacer por ti?",
    "¿Te ayudo con algo más?",
    "¿Hay algo más que quieras hacer?"
]

CONFIRMACIONES = [
    "¡Perfecto!",
    "¡Excelente!",
    "¡Genial!",
    "¡Muy bien!",
    "¡Estupendo!"
]

# ==============================
# Adaptador de "Fake S3" (memoria)
# ==============================
_FAKE_STORE = {}

class FakeS3Adapter:
    def __init__(self):
        logger.info("🧪 Usando FakeS3Adapter (memoria)")

    @staticmethod
    def _user_id_from_envelope(request_envelope):
        return request_envelope.context.system.user.user_id

    def get_attributes(self, request_envelope):
        uid = self._user_id_from_envelope(request_envelope)
        return _FAKE_STORE.get(uid, {})

    def save_attributes(self, request_envelope, attributes):
        uid = self._user_id_from_envelope(request_envelope)
        _FAKE_STORE[uid] = attributes or {}
        logger.info(f"FakeS3Adapter: guardados atributos para {uid}")

    def delete_attributes(self, request_envelope):
        uid = self._user_id_from_envelope(request_envelope)
        if uid in _FAKE_STORE:
            del _FAKE_STORE[uid]
            logger.info(f"FakeS3Adapter: atributos borrados para {uid}")

# ==============================
# Inicializar persistence adapter
# ==============================
if USE_FAKE_S3:
    persistence_adapter = FakeS3Adapter()
else:
    s3_bucket = os.environ.get("S3_PERSISTENCE_BUCKET")
    if not s3_bucket:
        raise RuntimeError("S3_PERSISTENCE_BUCKET es requerido cuando USE_FAKE_S3=false")
    logger.info(f"🪣 Usando S3Adapter con bucket: {s3_bucket}")
    persistence_adapter = S3Adapter(bucket_name=s3_bucket)

sb = CustomSkillBuilder(persistence_adapter=persistence_adapter)

# ==============================
# Cache en memoria con TTL
# ==============================
_CACHE = {}

def _cache_get(user_id):
    item = _CACHE.get(user_id)
    if not item:
        return None
    if datetime.now().timestamp() > item["expire_at"]:
        _CACHE.pop(user_id, None)
        return None
    return item["data"]

def _cache_put(user_id, data):
    _CACHE[user_id] = {
        "data": data,
        "expire_at": (datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)).timestamp()
    }

dynamodb = boto3.resource("dynamodb", region_name="us-east-1") if ENABLE_DDB_CACHE else None

class DatabaseManager:
    DDB_TABLE = "BibliotecaSkillCache"

    @staticmethod
    def _user_id(handler_input):
        return handler_input.request_envelope.context.system.user.user_id

    @staticmethod
    def _get_ddb_table():
        if not ENABLE_DDB_CACHE:
            return None
        try:
            table = dynamodb.Table(DatabaseManager.DDB_TABLE)
            table.load()
            return table
        except Exception as e:
            logger.warning(f"DDB deshabilitado o sin permisos: {e}")
            return None

    @staticmethod
    def get_user_data(handler_input):
        user_id = DatabaseManager._user_id(handler_input)

        # 1) Cache en memoria
        data = _cache_get(user_id)
        if data is not None:
            logger.info("⚡ Cache hit (memoria)")
            return data

        # 2) Cache en DDB (opcional)
        if ENABLE_DDB_CACHE:
            try:
                table = DatabaseManager._get_ddb_table()
                if table:
                    resp = table.get_item(Key={"user_id": user_id})
                    if "Item" in resp:
                        data = resp["Item"].get("data", {})
                        logger.info("⚡ Cache hit (DynamoDB)")
                        _cache_put(user_id, data)
                        return data
            except Exception as e:
                logger.warning(f"DDB get_item error: {e}")

        # 3) Persistencia principal
        attr_mgr = handler_input.attributes_manager
        persistent = attr_mgr.persistent_attributes
        if not persistent:
            persistent = DatabaseManager.initial_data()
            attr_mgr.persistent_attributes = persistent
            attr_mgr.save_persistent_attributes()

        # 4) Actualizar cachés
        _cache_put(user_id, persistent)
        if ENABLE_DDB_CACHE:
            try:
                table = DatabaseManager._get_ddb_table()
                if table:
                    table.put_item(Item={
                        "user_id": user_id,
                        "data": persistent,
                        "ttl": int((datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)).timestamp())
                    })
            except Exception as e:
                logger.warning(f"DDB put_item error: {e}")

        return persistent

    @staticmethod
    def save_user_data(handler_input, data):
        user_id = DatabaseManager._user_id(handler_input)

        # Persistencia principal
        attr_mgr = handler_input.attributes_manager
        attr_mgr.persistent_attributes = data
        attr_mgr.save_persistent_attributes()

        # Actualizar cachés
        _cache_put(user_id, data)

        if ENABLE_DDB_CACHE:
            try:
                table = DatabaseManager._get_ddb_table()
                if table:
                    table.put_item(Item={
                        "user_id": user_id,
                        "data": data,
                        "ttl": int((datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)).timestamp())
                    })
            except Exception as e:
                logger.warning(f"DDB put_item error: {e}")

    @staticmethod
    def initial_data():
        return {
            "libros_disponibles": [],
            "prestamos_activos": [],
            "historial_prestamos": [],
            "estadisticas": {
                "total_libros": 0,
                "total_prestamos": 0,
                "total_devoluciones": 0
            },
            "historial_conversaciones": [],
            "configuracion": {"limite_prestamos": 10, "dias_prestamo": 7},  # Aumentado el límite
            "usuario_frecuente": False
        }

# ==============================
# Helpers
# ==============================
def generar_id_unico():
    """Genera un ID único para libros y préstamos"""
    return str(uuid.uuid4())[:8]

def sincronizar_estados_libros(user_data):
    """Sincroniza los estados de los libros basándose en los préstamos activos"""
    libros = user_data.get("libros_disponibles", [])
    prestamos = user_data.get("prestamos_activos", [])
    
    # Primero, asegurar que todos los libros tengan ID
    for libro in libros:
        if not libro.get("id"):
            libro["id"] = generar_id_unico()
    
    # Luego, actualizar estados
    ids_prestados = {p.get("libro_id") for p in prestamos if p.get("libro_id")}
    
    for libro in libros:
        if libro.get("id") in ids_prestados:
            libro["estado"] = "prestado"
        else:
            libro["estado"] = "disponible"
    
    return user_data

def buscar_libro_por_titulo(libros, titulo_busqueda):
    """Busca libros por título y devuelve una lista de coincidencias"""
    titulo_busqueda = (titulo_busqueda or "").lower().strip()
    resultados = []
    for libro in libros:
        if isinstance(libro, dict):
            titulo_libro = (libro.get("titulo") or "").lower()
            if titulo_busqueda in titulo_libro or titulo_libro in titulo_busqueda:
                resultados.append(libro)
    return resultados

def buscar_libro_por_titulo_exacto(libros, titulo_busqueda):
    """Busca un libro por título y devuelve el primero que coincida"""
    titulo_busqueda = (titulo_busqueda or "").lower().strip()
    for libro in libros:
        if isinstance(libro, dict):
            titulo_libro = (libro.get("titulo") or "").lower()
            if titulo_busqueda in titulo_libro or titulo_libro in titulo_busqueda:
                return libro
    return None

def buscar_libros_por_autor(libros, autor_busqueda):
    autor_busqueda = (autor_busqueda or "").lower().strip()
    resultados = []
    for libro in libros:
        if isinstance(libro, dict):
            autor_libro = (libro.get("autor") or "").lower()
            if autor_busqueda in autor_libro or autor_libro in autor_busqueda:
                resultados.append(libro)
    return resultados

def generar_id_prestamo():
    return f"PREST-{datetime.now().strftime('%Y%m%d')}-{generar_id_unico()}"

def get_random_phrase(phrase_list):
    """Selecciona una frase aleatoria de una lista"""
    return random.choice(phrase_list)

# ==============================
# Handlers
# ==============================

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        try:
            # Limpiar sesión al inicio
            handler_input.attributes_manager.session_attributes = {}
            
            user_data = DatabaseManager.get_user_data(handler_input)
            
            # IMPORTANTE: Sincronizar estados al inicio
            user_data = sincronizar_estados_libros(user_data)
            DatabaseManager.save_user_data(handler_input, user_data)
            
            # Marcar si es usuario frecuente
            historial = user_data.get("historial_conversaciones", [])
            es_usuario_frecuente = len(historial) > 5
            
            user_data.setdefault("historial_conversaciones", []).append({
                "tipo": "inicio_sesion",
                "timestamp": datetime.now().isoformat(),
                "accion": "bienvenida"
            })
            DatabaseManager.save_user_data(handler_input, user_data)

            total_libros = len(user_data.get("libros_disponibles", []))
            prestamos_activos = len(user_data.get("prestamos_activos", []))

            # Saludo personalizado
            if es_usuario_frecuente and total_libros > 0:
                saludo = "¡Hola de nuevo! ¡Qué bueno verte por aquí!"
                estado = f" Veo que tienes {total_libros} libros en tu biblioteca"
                if prestamos_activos > 0:
                    estado += f" y {prestamos_activos} préstamos activos"
                estado += "."
            else:
                saludo = get_random_phrase(SALUDOS)
                if total_libros == 0:
                    estado = " Veo que es tu primera vez aquí. ¡Empecemos a construir tu biblioteca!"
                else:
                    estado = f" Tienes {total_libros} libros en tu colección."
            
            # Opciones disponibles
            opciones = " " + get_random_phrase(OPCIONES_MENU)
            pregunta = " " + get_random_phrase(PREGUNTAS_QUE_HACER)
            
            speak_output = saludo + estado + opciones + pregunta
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en LaunchRequest: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("¡Hola! Bienvenido a tu biblioteca. ¿En qué puedo ayudarte?")
                    .ask("¿Qué deseas hacer?")
                    .response
            )

class AgregarLibroIntentHandler(AbstractRequestHandler):
    """Handler para agregar libros"""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AgregarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            autor = ask_utils.get_slot_value(handler_input, "autor")
            tipo = ask_utils.get_slot_value(handler_input, "tipo")
            
            session_attrs = handler_input.attributes_manager.session_attributes
            
            logger.info(f"AgregarLibro - Título: {titulo}, Autor: {autor}, Tipo: {tipo}")
            logger.info(f"Session: {session_attrs}")
            
            # Recuperar valores de sesión si existen
            if session_attrs.get("agregando_libro"):
                titulo = titulo or session_attrs.get("titulo_temp")
                autor = autor or session_attrs.get("autor_temp")
                tipo = tipo or session_attrs.get("tipo_temp")
            
            # PASO 1: Pedir título
            if not titulo:
                session_attrs["agregando_libro"] = True
                session_attrs["esperando"] = "titulo"
                return (
                    handler_input.response_builder
                        .speak("¡Perfecto! Vamos a agregar un libro. ¿Cuál es el título?")
                        .ask("¿Cuál es el título del libro?")
                        .response
                )
            
            # Guardar título
            session_attrs["titulo_temp"] = titulo
            session_attrs["agregando_libro"] = True
            
            # PASO 2: Pedir autor
            if not autor:
                session_attrs["esperando"] = "autor"
                return (
                    handler_input.response_builder
                        .speak(f"¡'{titulo}' suena interesante! ¿Quién es el autor? Si no lo sabes, di: no sé.")
                        .ask("¿Quién es el autor?")
                        .response
                )
            
            # Guardar autor
            session_attrs["autor_temp"] = autor
            
            # PASO 3: Pedir tipo
            if not tipo:
                session_attrs["esperando"] = "tipo"
                autor_text = f" de {autor}" if autor and autor.lower() not in ["no sé", "no se"] else ""
                return (
                    handler_input.response_builder
                        .speak(f"Casi listo con '{titulo}'{autor_text}. ¿De qué tipo o género es? Si no sabes, di: no sé.")
                        .ask("¿De qué tipo es el libro?")
                        .response
                )
            
            # Normalizar valores
            if autor and autor.lower() in ["no sé", "no se", "no lo sé"]:
                autor = "Desconocido"
            if tipo and tipo.lower() in ["no sé", "no se", "no lo sé"]:
                tipo = "Sin categoría"
            
            # Guardar el libro
            user_data = DatabaseManager.get_user_data(handler_input)
            libros = user_data.get("libros_disponibles", [])
            
            # Verificar duplicado
            for libro in libros:
                if libro.get("titulo", "").lower() == titulo.lower():
                    handler_input.attributes_manager.session_attributes = {}
                    return (
                        handler_input.response_builder
                            .speak(f"'{titulo}' ya está en tu biblioteca. " + get_random_phrase(ALGO_MAS))
                            .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                            .response
                    )
            
            nuevo_libro = {
                "id": generar_id_unico(),
                "titulo": titulo,
                "autor": autor if autor else "Desconocido",
                "tipo": tipo if tipo else "Sin categoría",
                "fecha_agregado": datetime.now().isoformat(),
                "total_prestamos": 0,
                "estado": "disponible"
            }
            
            libros.append(nuevo_libro)
            user_data["libros_disponibles"] = libros
            
            stats = user_data.setdefault("estadisticas", {})
            stats["total_libros"] = len(libros)
            
            DatabaseManager.save_user_data(handler_input, user_data)
            
            # Limpiar sesión
            handler_input.attributes_manager.session_attributes = {}
            
            speak_output = f"¡Perfecto! He agregado '{titulo}'"
            if autor and autor != "Desconocido":
                speak_output += f" de {autor}"
            if tipo and tipo != "Sin categoría":
                speak_output += f", categoría {tipo}"
            speak_output += f". Ahora tienes {len(libros)} libros en tu biblioteca. "
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )

        except Exception as e:
            logger.error(f"Error en AgregarLibro: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema agregando el libro. Intentemos de nuevo.")
                    .ask("¿Qué libro quieres agregar?")
                    .response
            )


class ContinuarAgregarHandler(AbstractRequestHandler):
    """Handler para continuar el proceso de agregar cuando el usuario responde"""
    def can_handle(self, handler_input):
        session_attrs = handler_input.attributes_manager.session_attributes
        # Solo manejar si estamos agregando Y no es el intent de agregar
        return (session_attrs.get("agregando_libro") and 
                not ask_utils.is_intent_name("AgregarLibroIntent")(handler_input) and
                not ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) and
                not ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))
    
    def handle(self, handler_input):
        try:
            session_attrs = handler_input.attributes_manager.session_attributes
            esperando = session_attrs.get("esperando")
            
            # Intentar obtener el valor de la respuesta
            valor = None
            request = handler_input.request_envelope.request
            
            if hasattr(request, 'intent') and request.intent:
                intent_name = request.intent.name if hasattr(request.intent, 'name') else None
                logger.info(f"Intent detectado: {intent_name}")
                
                # Primero, buscar el slot 'respuesta' del RespuestaGeneralIntent
                if intent_name == "RespuestaGeneralIntent":
                    valor = ask_utils.get_slot_value(handler_input, "respuesta")
                    logger.info(f"Respuesta general capturada: {valor}")
                
                # Si no es RespuestaGeneralIntent, buscar en cualquier slot disponible
                if not valor and hasattr(request.intent, 'slots') and request.intent.slots:
                    for slot_name, slot in request.intent.slots.items():
                        if slot and hasattr(slot, 'value') and slot.value:
                            valor = slot.value
                            logger.info(f"Valor encontrado en slot {slot_name}: {valor}")
                            break
                
                # IMPORTANTE: Para intents mal interpretados, intentar capturar el utterance original
                # Esto es un workaround cuando Alexa malinterpreta la respuesta
                if not valor and intent_name in ["LimpiarCacheIntent", "SiguientePaginaIntent", 
                                                 "ListarLibrosIntent", "BuscarLibroIntent"]:
                    # Cuando el usuario dice algo que Alexa malinterpreta,
                    # pedimos que repita con una frase más específica
                    if esperando == "autor":
                        return (
                            handler_input.response_builder
                                .speak("No entendí bien. Por favor di: 'el autor es' seguido del nombre. O di: no sé el autor.")
                                .ask("¿Quién es el autor? Di: 'el autor es' y el nombre.")
                                .response
                        )
                    elif esperando == "tipo":
                        return (
                            handler_input.response_builder
                                .speak("No entendí bien. Por favor di: 'el tipo es' seguido del género. O di: no sé el tipo.")
                                .ask("¿De qué tipo es? Di: 'el tipo es' y el género.")
                                .response
                        )
                    elif esperando == "titulo":
                        return (
                            handler_input.response_builder
                                .speak("No entendí bien. Por favor di: 'el título es' seguido del nombre del libro.")
                                .ask("¿Cuál es el título? Di: 'el título es' y el nombre.")
                                .response
                        )
            
            logger.info(f"ContinuarAgregar - Esperando: {esperando}, Valor: {valor}")
            
            # Procesar según lo que estamos esperando
            if esperando == "titulo":
                if valor:
                    session_attrs["titulo_temp"] = valor
                    session_attrs["esperando"] = "autor"
                    return (
                        handler_input.response_builder
                            .speak(f"¡'{valor}' suena interesante! ¿Quién es el autor? Si no lo sabes, di: no sé el autor.")
                            .ask("¿Quién es el autor? Puedes decir: 'el autor es' y el nombre, o 'no sé el autor'.")
                            .response
                    )
                else:
                    return (
                        handler_input.response_builder
                            .speak("No entendí el título. Por favor di: 'el título es' seguido del nombre del libro.")
                            .ask("¿Cuál es el título del libro?")
                            .response
                    )
            
            elif esperando == "autor":
                # Manejar variaciones de "no sé"
                if not valor or valor.lower() in ["no sé", "no se", "no lo sé", "no lo se", 
                                                  "no sé el autor", "no se el autor"]:
                    valor = "Desconocido"
                # Limpiar prefijos comunes
                elif valor.lower().startswith("el autor es "):
                    valor = valor[12:].strip()
                elif valor.lower().startswith("es "):
                    valor = valor[3:].strip()
                
                session_attrs["autor_temp"] = valor
                session_attrs["esperando"] = "tipo"
                
                titulo = session_attrs.get("titulo_temp")
                autor_text = f" de {valor}" if valor != "Desconocido" else ""
                
                return (
                    handler_input.response_builder
                        .speak(f"Perfecto, '{titulo}'{autor_text}. ¿De qué tipo o género es? Por ejemplo: novela, fantasía, ciencia ficción. Si no sabes, di: no sé el tipo.")
                        .ask("¿De qué tipo es el libro? Puedes decir: 'el tipo es' y el género, o 'no sé el tipo'.")
                        .response
                )
            
            elif esperando == "tipo":
                # Manejar variaciones de "no sé"
                if not valor or valor.lower() in ["no sé", "no se", "no lo sé", "no lo se",
                                                  "no sé el tipo", "no se el tipo"]:
                    valor = "Sin categoría"
                # Limpiar prefijos comunes
                elif valor.lower().startswith("el tipo es "):
                    valor = valor[11:].strip()
                elif valor.lower().startswith("es "):
                    valor = valor[3:].strip()
                
                # Guardar el libro
                titulo_final = session_attrs.get("titulo_temp")
                autor_final = session_attrs.get("autor_temp", "Desconocido")
                tipo_final = valor
                
                user_data = DatabaseManager.get_user_data(handler_input)
                libros = user_data.get("libros_disponibles", [])
                
                # Verificar duplicado
                for libro in libros:
                    if libro.get("titulo", "").lower() == titulo_final.lower():
                        handler_input.attributes_manager.session_attributes = {}
                        return (
                            handler_input.response_builder
                                .speak(f"'{titulo_final}' ya está en tu biblioteca. " + get_random_phrase(ALGO_MAS))
                                .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                                .response
                        )
                
                nuevo_libro = {
                    "id": generar_id_unico(),
                    "titulo": titulo_final,
                    "autor": autor_final,
                    "tipo": tipo_final,
                    "fecha_agregado": datetime.now().isoformat(),
                    "total_prestamos": 0,
                    "estado": "disponible"
                }
                
                libros.append(nuevo_libro)
                user_data["libros_disponibles"] = libros
                
                stats = user_data.setdefault("estadisticas", {})
                stats["total_libros"] = len(libros)
                
                DatabaseManager.save_user_data(handler_input, user_data)
                
                # Limpiar sesión
                handler_input.attributes_manager.session_attributes = {}
                
                speak_output = f"¡Perfecto! He agregado '{titulo_final}'"
                if autor_final != "Desconocido":
                    speak_output += f" de {autor_final}"
                if tipo_final != "Sin categoría":
                    speak_output += f", categoría {tipo_final}"
                speak_output += f". Ahora tienes {len(libros)} libros en tu biblioteca. "
                speak_output += get_random_phrase(ALGO_MAS)
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
            
            # Si llegamos aquí, algo salió mal
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema. Empecemos de nuevo. ¿Qué libro quieres agregar?")
                    .ask("¿Qué libro quieres agregar?")
                    .response
            )
            
        except Exception as e:
            logger.error(f"Error en ContinuarAgregar: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema. Intentemos agregar el libro de nuevo.")
                    .ask("¿Qué libro quieres agregar?")
                    .response
            )




class ListarLibrosIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ListarLibrosIntent")(handler_input)

    def handle(self, handler_input):
        try:
            # Obtener parámetros de filtrado
            filtro = ask_utils.get_slot_value(handler_input, "filtro_tipo")
            autor = ask_utils.get_slot_value(handler_input, "autor")
            
            user_data = DatabaseManager.get_user_data(handler_input)
            
            # IMPORTANTE: Sincronizar estados antes de listar
            user_data = sincronizar_estados_libros(user_data)
            DatabaseManager.save_user_data(handler_input, user_data)
            
            session_attrs = handler_input.attributes_manager.session_attributes
            
            todos_libros = user_data.get("libros_disponibles", [])
            prestamos = user_data.get("prestamos_activos", [])
            
            if not todos_libros:
                speak_output = "Aún no tienes libros en tu biblioteca. ¿Te gustaría agregar el primero? Solo di: agrega un libro."
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Quieres agregar tu primer libro?")
                        .response
                )
            
            # Filtrar libros según el criterio
            libros_filtrados = todos_libros.copy()
            titulo_filtro = ""
            
            if autor:
                libros_filtrados = buscar_libros_por_autor(libros_filtrados, autor)
                titulo_filtro = f" de {autor}"
            elif filtro:
                if filtro.lower() in ["prestados", "prestado"]:
                    ids_prestados = [p.get("libro_id") for p in prestamos]
                    libros_filtrados = [l for l in libros_filtrados if l.get("id") in ids_prestados]
                    titulo_filtro = " prestados"
                elif filtro.lower() in ["disponibles", "disponible"]:
                    ids_prestados = [p.get("libro_id") for p in prestamos]
                    libros_filtrados = [l for l in libros_filtrados if l.get("id") not in ids_prestados]
                    titulo_filtro = " disponibles"
            
            if not libros_filtrados:
                speak_output = f"No encontré libros{titulo_filtro}. " + get_random_phrase(ALGO_MAS)
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
            
            # Paginación
            pagina_actual = session_attrs.get("pagina_libros", 0)
            inicio = pagina_actual * LIBROS_POR_PAGINA
            fin = min(inicio + LIBROS_POR_PAGINA, len(libros_filtrados))
            
            # Si son 10 o menos, listar todos
            if len(libros_filtrados) <= LIBROS_POR_PAGINA:
                speak_output = f"Tienes {len(libros_filtrados)} libros{titulo_filtro}: "
                titulos = [f"'{l.get('titulo', 'Sin título')}'" for l in libros_filtrados]
                speak_output += ", ".join(titulos) + ". "
                speak_output += get_random_phrase(ALGO_MAS)
                
                # Limpiar paginación
                session_attrs["pagina_libros"] = 0
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
            
            # Si son más de 10, paginar
            libros_pagina = libros_filtrados[inicio:fin]
            
            if pagina_actual == 0:
                speak_output = f"Tienes {len(libros_filtrados)} libros{titulo_filtro}. "
                speak_output += f"Te los voy a mostrar de {LIBROS_POR_PAGINA} en {LIBROS_POR_PAGINA}. "
            else:
                speak_output = f"Página {pagina_actual + 1}. "
            
            speak_output += f"Libros del {inicio + 1} al {fin}: "
            titulos = [f"'{l.get('titulo', 'Sin título')}'" for l in libros_pagina]
            speak_output += ", ".join(titulos) + ". "
            
            if fin < len(libros_filtrados):
                speak_output += f"Quedan {len(libros_filtrados) - fin} libros más. Di 'siguiente' para continuar o 'salir' para terminar."
                session_attrs["pagina_libros"] = pagina_actual + 1
                session_attrs["listando_libros"] = True
                session_attrs["libros_filtrados"] = libros_filtrados
                ask_output = "¿Quieres ver más libros? Di 'siguiente' o 'salir'."
            else:
                speak_output += "Esos son todos los libros. " + get_random_phrase(ALGO_MAS)
                session_attrs["pagina_libros"] = 0
                session_attrs["listando_libros"] = False
                ask_output = get_random_phrase(PREGUNTAS_QUE_HACER)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(ask_output)
                    .response
            )
            
        except Exception as e:
            logger.error(f"Error en ListarLibros: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema consultando tu biblioteca. ¿Intentamos de nuevo?")
                    .ask("¿Qué te gustaría hacer?")
                    .response
            )

class PrestarLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("PrestarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            nombre_persona = ask_utils.get_slot_value(handler_input, "nombre_persona")

            if not titulo:
                prompts = [
                    "¡Claro! ¿Qué libro quieres prestar?",
                    "Por supuesto. ¿Cuál libro vas a prestar?",
                    "¡Perfecto! ¿Qué libro necesitas prestar?"
                ]
                return (
                    handler_input.response_builder
                        .speak(random.choice(prompts))
                        .ask("¿Cuál es el título del libro?")
                        .response
                )

            user_data = DatabaseManager.get_user_data(handler_input)
            
            # IMPORTANTE: Sincronizar estados antes de prestar
            user_data = sincronizar_estados_libros(user_data)
            
            libros = user_data.get("libros_disponibles", [])
            prestamos = user_data.get("prestamos_activos", [])

            # Buscar el libro específico
            libro = buscar_libro_por_titulo_exacto(libros, titulo)
            
            if not libro:
                speak_output = f"Hmm, no encuentro '{titulo}' en tu biblioteca. "
                if libros:
                    # Mostrar solo libros disponibles (no prestados)
                    ids_prestados = [p.get("libro_id") for p in prestamos]
                    disponibles = [l for l in libros if l.get("id") not in ids_prestados]
                    if disponibles:
                        ejemplos = [l.get("titulo") for l in disponibles[:2]]
                        speak_output += f"Tienes disponibles: {', '.join(ejemplos)}. ¿Cuál quieres prestar?"
                    else:
                        speak_output += "Todos tus libros están prestados actualmente."
                else:
                    speak_output += "De hecho, aún no tienes libros en tu biblioteca."
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Qué libro quieres prestar?")
                        .response
                )

            # Verificar que el libro tiene ID
            if not libro.get("id"):
                libro["id"] = generar_id_unico()
                # Actualizar el libro en la lista
                for idx, l in enumerate(libros):
                    if l.get("titulo") == libro.get("titulo"):
                        libros[idx]["id"] = libro["id"]
                        break

            # Verificar si ESTE libro específico ya está prestado
            libro_ya_prestado = False
            prestamo_existente = None
            for p in prestamos:
                if p.get("libro_id") == libro.get("id"):
                    libro_ya_prestado = True
                    prestamo_existente = p
                    break

            if libro_ya_prestado:
                speak_output = f"'{libro['titulo']}' ya está prestado a {prestamo_existente.get('persona', 'alguien')}. "
                # Sugerir otros libros disponibles
                ids_prestados = [p.get("libro_id") for p in prestamos]
                disponibles = [l for l in libros if l.get("id") not in ids_prestados]
                if disponibles:
                    speak_output += "¿Quieres prestar otro libro? "
                    ejemplos = [l.get("titulo") for l in disponibles[:2]]
                    speak_output += f"Tienes disponibles: {', '.join(ejemplos)}."
                else:
                    speak_output += "No tienes más libros disponibles para prestar."
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Qué otro libro quieres prestar?")
                        .response
                )

            # Crear préstamo
            prestamo = {
                "id": generar_id_prestamo(),
                "libro_id": libro["id"],
                "titulo": libro["titulo"],
                "persona": nombre_persona if nombre_persona else "un amigo",
                "fecha_prestamo": datetime.now().isoformat(),
                "fecha_limite": (datetime.now() + timedelta(days=7)).isoformat(),
                "estado": "activo"
            }

            prestamos.append(prestamo)
            user_data["prestamos_activos"] = prestamos
            
            # Marcar el libro como prestado
            for l in libros:
                if l.get("id") == libro.get("id"):
                    l["estado"] = "prestado"
                    l["total_prestamos"] = l.get("total_prestamos", 0) + 1
                    break

            stats = user_data.get("estadisticas", {})
            stats["total_prestamos"] = stats.get("total_prestamos", 0) + 1

            DatabaseManager.save_user_data(handler_input, user_data)

            # Respuesta natural
            confirmacion = get_random_phrase(CONFIRMACIONES)
            persona_text = f" a {nombre_persona}" if nombre_persona else ""
            fecha_limite = datetime.fromisoformat(prestamo['fecha_limite']).strftime("%d de %B")
            
            speak_output = f"{confirmacion} He registrado el préstamo de '{libro['titulo']}'{persona_text}. "
            speak_output += f"La fecha de devolución es el {fecha_limite}. "
            
            # Informar cuántos libros disponibles quedan
            ids_prestados = [p.get("libro_id") for p in prestamos]
            disponibles = len([l for l in libros if l.get("id") not in ids_prestados])
            if disponibles > 0:
                speak_output += f"Te quedan {disponibles} libros disponibles. "
            else:
                speak_output += "Ya no tienes más libros disponibles para prestar. "
            
            speak_output += get_random_phrase(ALGO_MAS)

            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en PrestarLibro: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Ups, tuve un problema registrando el préstamo. ¿Lo intentamos de nuevo?")
                    .ask("¿Qué libro quieres prestar?")
                    .response
            )

class LimpiarCacheIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("LimpiarCacheIntent")(handler_input)

    def handle(self, handler_input):
        try:
            user_id = DatabaseManager._user_id(handler_input)
            
            # Limpiar cache en memoria
            global _CACHE
            if user_id in _CACHE:
                del _CACHE[user_id]
            
            # Limpiar sesión
            handler_input.attributes_manager.session_attributes = {}
            
            # Recargar datos desde S3/FakeS3
            user_data = DatabaseManager.get_user_data(handler_input)
            
            # IMPORTANTE: Sincronizar estados
            user_data = sincronizar_estados_libros(user_data)
            
            # Guardar datos sincronizados
            DatabaseManager.save_user_data(handler_input, user_data)
            
            libros = user_data.get("libros_disponibles", [])
            prestamos = user_data.get("prestamos_activos", [])
            
            speak_output = "He limpiado el cache y sincronizado tu biblioteca. "
            speak_output += f"Tienes {len(libros)} libros en total y {len(prestamos)} préstamos activos. "
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error limpiando cache: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema limpiando el cache. Intenta de nuevo.")
                    .ask("¿Qué deseas hacer?")
                    .response
            )

# Añadir los demás handlers (los que no cambié)...
class BuscarLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("BuscarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            
            if not titulo:
                return (
                    handler_input.response_builder
                        .speak("¿Qué libro quieres buscar?")
                        .ask("Dime el título del libro que buscas.")
                        .response
                )
            
            user_data = DatabaseManager.get_user_data(handler_input)
            user_data = sincronizar_estados_libros(user_data)
            libros = user_data.get("libros_disponibles", [])
            
            libros_encontrados = buscar_libro_por_titulo(libros, titulo)
            
            if not libros_encontrados:
                speak_output = f"No encontré ningún libro con el título '{titulo}' en tu biblioteca. "
                speak_output += get_random_phrase(ALGO_MAS)
            elif len(libros_encontrados) == 1:
                libro = libros_encontrados[0]
                speak_output = f"Encontré '{libro['titulo']}'. "
                speak_output += f"Autor: {libro.get('autor', 'Desconocido')}. "
                speak_output += f"Tipo: {libro.get('tipo', 'Sin categoría')}. "
                speak_output += f"Estado: {libro.get('estado', 'disponible')}. "
                
                if libro.get('total_prestamos', 0) > 0:
                    speak_output += f"Ha sido prestado {libro['total_prestamos']} veces. "
                
                speak_output += get_random_phrase(ALGO_MAS)
            else:
                speak_output = f"Encontré {len(libros_encontrados)} libros que coinciden con '{titulo}': "
                for libro in libros_encontrados[:3]:
                    speak_output += f"'{libro['titulo']}' de {libro.get('autor', 'Desconocido')}, "
                speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
            
        except Exception as e:
            logger.error(f"Error en BuscarLibro: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema buscando el libro. ¿Intentamos de nuevo?")
                    .ask("¿Qué libro buscas?")
                    .response
            )

class DevolverLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("DevolverLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            id_prestamo = ask_utils.get_slot_value(handler_input, "id_prestamo")

            if not titulo and not id_prestamo:
                prompts = [
                    "¡Qué bien! ¿Qué libro te devolvieron?",
                    "Perfecto, vamos a registrar la devolución. ¿Cuál libro es?",
                    "¡Excelente! ¿Qué libro estás devolviendo?"
                ]
                return (
                    handler_input.response_builder
                        .speak(random.choice(prompts))
                        .ask("¿Cuál es el título del libro?")
                        .response
                )

            user_data = DatabaseManager.get_user_data(handler_input)
            prestamos = user_data.get("prestamos_activos", [])

            if not prestamos:
                speak_output = "No tienes libros prestados en este momento. Todos tus libros están en su lugar. "
                speak_output += get_random_phrase(ALGO_MAS)
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )

            prestamo_encontrado = None
            indice = -1

            for i, p in enumerate(prestamos):
                if id_prestamo and p.get("id") == id_prestamo:
                    prestamo_encontrado = p
                    indice = i
                    break
                elif titulo and titulo.lower() in (p.get("titulo", "").lower()):
                    prestamo_encontrado = p
                    indice = i
                    break

            if not prestamo_encontrado:
                # Ayudar al usuario listando préstamos
                if len(prestamos) == 1:
                    p = prestamos[0]
                    sugerencia = f"Solo tienes prestado '{p.get('titulo')}' a {p.get('persona')}. ¿Es ese?"
                else:
                    titulos_prestados = [f"'{p.get('titulo')}'" for p in prestamos[:3]]
                    sugerencia = f"Tienes prestados: {', '.join(titulos_prestados)}. ¿Cuál de estos es?"
                
                return (
                    handler_input.response_builder
                        .speak(f"Hmm, no encuentro ese libro en los préstamos. {sugerencia}")
                        .ask("¿Cuál libro quieres devolver?")
                        .response
                )

            # Procesar devolución
            prestamos.pop(indice)
            prestamo_encontrado["fecha_devolucion"] = datetime.now().isoformat()
            prestamo_encontrado["estado"] = "devuelto"

            # Calcular si fue devuelto a tiempo
            fecha_limite = datetime.fromisoformat(prestamo_encontrado["fecha_limite"])
            devuelto_a_tiempo = datetime.now() <= fecha_limite

            historial = user_data.get("historial_prestamos", [])
            historial.append(prestamo_encontrado)

            libros = user_data.get("libros_disponibles", [])
            for l in libros:
                if l.get("id") == prestamo_encontrado.get("libro_id"):
                    l["estado"] = "disponible"
                    break

            user_data["prestamos_activos"] = prestamos
            user_data["historial_prestamos"] = historial
            stats = user_data.get("estadisticas", {})
            stats["total_devoluciones"] = stats.get("total_devoluciones", 0) + 1

            DatabaseManager.save_user_data(handler_input, user_data)

            # Respuesta natural
            confirmacion = get_random_phrase(CONFIRMACIONES)
            speak_output = f"{confirmacion} He registrado la devolución de '{prestamo_encontrado['titulo']}'. "
            
            if devuelto_a_tiempo:
                speak_output += "¡Fue devuelto a tiempo! "
            else:
                speak_output += "Fue devuelto un poco tarde, pero no hay problema. "
            
            speak_output += "Espero que lo hayan disfrutado. "
            
            if prestamos:
                speak_output += f"Aún tienes {len(prestamos)} "
                speak_output += "libro prestado. " if len(prestamos) == 1 else "libros prestados. "
            
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en DevolverLibro: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Tuve un problema registrando la devolución. ¿Lo intentamos de nuevo?")
                    .ask("¿Qué libro quieres devolver?")
                    .response
            )

class ConsultarPrestamosIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ConsultarPrestamosIntent")(handler_input)

    def handle(self, handler_input):
        try:
            user_data = DatabaseManager.get_user_data(handler_input)
            user_data = sincronizar_estados_libros(user_data)
            prestamos = user_data.get("prestamos_activos", [])
            
            if not prestamos:
                speak_output = "¡Excelente! No tienes ningún libro prestado en este momento. Todos están en su lugar. "
                speak_output += get_random_phrase(ALGO_MAS)
            else:
                # Introducción variada
                if len(prestamos) == 1:
                    speak_output = "Déjame ver... Solo tienes un libro prestado: "
                else:
                    speak_output = f"Déjame revisar... Tienes {len(prestamos)} libros prestados: "
                
                # Listar préstamos con detalles
                detalles = []
                hay_vencidos = False
                hay_proximos = False
                
                for p in prestamos[:5]:
                    detalle = f"'{p['titulo']}' está con {p.get('persona', 'alguien')}"
                    
                    # Calcular días restantes
                    fecha_limite = datetime.fromisoformat(p['fecha_limite'])
                    dias_restantes = (fecha_limite - datetime.now()).days
                    
                    if dias_restantes < 0:
                        detalle += " (¡ya venció!)"
                        hay_vencidos = True
                    elif dias_restantes == 0:
                        detalle += " (vence hoy)"
                        hay_proximos = True
                    elif dias_restantes <= 2:
                        detalle += f" (vence en {dias_restantes} días)"
                        hay_proximos = True
                    
                    detalles.append(detalle)
                
                speak_output += "; ".join(detalles) + ". "
                
                if len(prestamos) > 5:
                    speak_output += f"Y {len(prestamos) - 5} más. "
                
                # Agregar advertencias si es necesario
                if hay_vencidos:
                    speak_output += "Te sugiero pedir la devolución de los libros vencidos. "
                elif hay_proximos:
                    speak_output += "Algunos están por vencer, ¡no lo olvides! "
                
                speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en ConsultarPrestamos: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema consultando los préstamos. ¿Intentamos de nuevo?")
                    .ask("¿Qué más deseas hacer?")
                    .response
            )

class ConsultarDevueltosIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ConsultarDevueltosIntent")(handler_input)

    def handle(self, handler_input):
        try:
            user_data = DatabaseManager.get_user_data(handler_input)
            historial = user_data.get("historial_prestamos", [])
            
            if not historial:
                speak_output = "Aún no has registrado devoluciones. Cuando prestes libros y te los devuelvan, aparecerán aquí. "
            else:
                total = len(historial)
                speak_output = f"Has registrado {total} "
                speak_output += "devolución en total. " if total == 1 else "devoluciones en total. "
                
                # Mostrar TODOS los títulos (o hasta un máximo razonable)
                if total <= 10:
                    speak_output += "Los libros devueltos son: "
                    detalles = []
                    for h in historial:
                        detalle = f"'{h.get('titulo', 'Sin título')}'"
                        if h.get('persona') and h['persona'] not in ['Alguien', 'un amigo']:
                            detalle += f" que prestaste a {h['persona']}"
                        detalles.append(detalle)
                    speak_output += ", ".join(detalles) + ". "
                else:
                    # Si son muchos, mostrar los últimos 5
                    recientes = historial[-5:]
                    speak_output += "Los 5 más recientes son: "
                    detalles = []
                    for h in reversed(recientes):
                        detalle = f"'{h.get('titulo', 'Sin título')}'"
                        if h.get('persona') and h['persona'] not in ['Alguien', 'un amigo']:
                            detalle += f" a {h['persona']}"
                        detalles.append(detalle)
                    speak_output += ", ".join(detalles) + ". "
            
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en ConsultarDevueltos: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema consultando el historial.")
                    .ask("¿Qué más deseas hacer?")
                    .response
            )

class MostrarOpcionesIntentHandler(AbstractRequestHandler):
    """Handler para cuando el usuario pide que le repitan las opciones"""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("MostrarOpcionesIntent")(handler_input)

    def handle(self, handler_input):
        try:
            user_data = DatabaseManager.get_user_data(handler_input)
            total_libros = len(user_data.get("libros_disponibles", []))
            
            intro = "¡Por supuesto! "
            opciones = get_random_phrase(OPCIONES_MENU)
            
            # Agregar contexto si es útil
            if total_libros == 0:
                contexto = " Como aún no tienes libros, te sugiero empezar agregando algunos."
            elif len(user_data.get("prestamos_activos", [])) > 0:
                contexto = " Recuerda que tienes algunos libros prestados."
            else:
                contexto = ""
            
            pregunta = " " + get_random_phrase(PREGUNTAS_QUE_HACER)
            
            speak_output = intro + opciones + contexto + pregunta
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error mostrando opciones: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Puedo ayudarte a gestionar tu biblioteca. ¿Qué te gustaría hacer?")
                    .ask("¿En qué puedo ayudarte?")
                    .response
            )

class SiguientePaginaIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SiguientePaginaIntent")(handler_input)

    def handle(self, handler_input):
        try:
            session_attrs = handler_input.attributes_manager.session_attributes
            
            if not session_attrs.get("listando_libros"):
                speak_output = "No estoy mostrando una lista en este momento. ¿Quieres ver tus libros?"
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Quieres que liste tus libros?")
                        .response
                )
            
            # Continuar con la paginación
            handler = ListarLibrosIntentHandler()
            return handler.handle(handler_input)
            
        except Exception as e:
            logger.error(f"Error en SiguientePagina: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema. ¿Qué te gustaría hacer?")
                    .ask("¿En qué puedo ayudarte?")
                    .response
            )

class SalirListadoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SalirListadoIntent")(handler_input)

    def handle(self, handler_input):
        # Limpiar estado de paginación
        session_attrs = handler_input.attributes_manager.session_attributes
        session_attrs["pagina_libros"] = 0
        session_attrs["listando_libros"] = False
        
        speak_output = "De acuerdo, terminé de mostrar los libros. " + get_random_phrase(ALGO_MAS)
        
        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                .response
        )

# ==============================
# Handlers estándar
# ==============================
class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        speak_output = (
            "¡Por supuesto! Te explico cómo funciona tu biblioteca. "
            "Puedes agregar libros nuevos diciendo 'agrega un libro', "
            "ver todos tus libros con 'lista mis libros', "
            "buscar un libro específico con 'busca' y el título, "
            "prestar un libro diciendo 'presta' seguido del título, "
            "registrar devoluciones con 'devuelvo' y el título, "
            "o consultar tus préstamos activos preguntando 'qué libros tengo prestados'. "
            "¿Qué te gustaría hacer primero?"
        )
        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask("¿Con qué te ayudo?")
                .response
        )

class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # Limpiar sesión al salir
        handler_input.attributes_manager.session_attributes = {}
        
        despedidas = [
            "¡Hasta luego! Que disfrutes tu lectura.",
            "¡Nos vemos pronto! Espero que disfrutes tus libros.",
            "¡Adiós! Fue un gusto ayudarte con tu biblioteca.",
            "¡Hasta la próxima! Feliz lectura.",
            "¡Que tengas un excelente día! Disfruta tus libros."
        ]
        
        return (
            handler_input.response_builder
                .speak(random.choice(despedidas))
                .response
        )

class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # Limpiar sesión
        handler_input.attributes_manager.session_attributes = {}
        return handler_input.response_builder.response

class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        session_attrs = handler_input.attributes_manager.session_attributes
        
        # Si estamos agregando un libro, manejar las respuestas
        if session_attrs.get("agregando_libro"):
            paso_actual = session_attrs.get("paso_actual")
            
            # Intentar obtener el texto del usuario del request
            request = handler_input.request_envelope.request
            
            # Para el fallback, Alexa a veces incluye el texto en el intent name o en slots genéricos
            # Vamos a asumir que el usuario respondió correctamente
            
            if paso_actual == "titulo":
                # El usuario probablemente dijo el título pero Alexa no lo reconoció
                return (
                    handler_input.response_builder
                        .speak("No entendí bien el título. ¿Puedes repetirlo más despacio?")
                        .ask("¿Cuál es el título del libro?")
                        .response
                )
            
            elif paso_actual == "autor":
                # Asumimos que dijo "no sé" o un nombre no reconocido
                session_attrs["autor_temp"] = "Desconocido"
                session_attrs["paso_actual"] = "tipo"
                titulo = session_attrs.get("titulo_temp")
                
                return (
                    handler_input.response_builder
                        .speak(f"De acuerdo, continuemos con '{titulo}'. ¿De qué tipo o género es? Por ejemplo: novela, fantasía, historia. Si no sabes, di: no sé.")
                        .ask("¿De qué tipo es el libro?")
                        .response
                )
            
            elif paso_actual == "tipo":
                # Asumimos que dijo "no sé" o un tipo no reconocido
                titulo_final = session_attrs.get("titulo_temp")
                autor_final = session_attrs.get("autor_temp", "Desconocido")
                tipo_final = "Sin categoría"
                
                # Guardar el libro
                user_data = DatabaseManager.get_user_data(handler_input)
                libros = user_data.get("libros_disponibles", [])
                
                # Verificar duplicado
                for libro in libros:
                    if libro.get("titulo", "").lower() == titulo_final.lower():
                        handler_input.attributes_manager.session_attributes = {}
                        return (
                            handler_input.response_builder
                                .speak(f"'{titulo_final}' ya está en tu biblioteca. " + get_random_phrase(ALGO_MAS))
                                .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                                .response
                        )
                
                nuevo_libro = {
                    "id": generar_id_unico(),
                    "titulo": titulo_final,
                    "autor": autor_final,
                    "tipo": tipo_final,
                    "fecha_agregado": datetime.now().isoformat(),
                    "total_prestamos": 0,
                    "estado": "disponible"
                }
                
                libros.append(nuevo_libro)
                user_data["libros_disponibles"] = libros
                
                # Actualizar estadísticas
                stats = user_data.setdefault("estadisticas", {})
                stats["total_libros"] = len(libros)
                
                DatabaseManager.save_user_data(handler_input, user_data)
                
                # Limpiar sesión
                handler_input.attributes_manager.session_attributes = {}
                
                speak_output = f"¡Perfecto! He agregado '{titulo_final}'"
                if autor_final != "Desconocido":
                    speak_output += f" de {autor_final}"
                speak_output += f". Ahora tienes {len(libros)} libros en tu biblioteca. "
                speak_output += get_random_phrase(ALGO_MAS)
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
        
        # Si estamos listando libros con paginación
        if session_attrs.get("listando_libros"):
            speak_output = "No entendí eso. ¿Quieres ver más libros? Di 'siguiente' para continuar o 'salir' para terminar."
            ask_output = "Di 'siguiente' o 'salir'."
        else:
            # Comportamiento normal del fallback
            respuestas = [
                "Disculpa, no entendí eso. ¿Podrías repetirlo de otra forma?",
                "Hmm, no estoy seguro de qué quisiste decir. ¿Me lo puedes decir de otra manera?",
                "Perdón, no comprendí. ¿Puedes intentarlo de nuevo?"
            ]
            
            speak_output = random.choice(respuestas)
            speak_output += " Recuerda que puedo ayudarte a agregar libros, listarlos, prestarlos o registrar devoluciones."
            ask_output = "¿Qué te gustaría hacer?"
        
        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(ask_output)
                .response
        )

class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(f"Exception: {exception}", exc_info=True)
        # Limpiar sesión en caso de error
        handler_input.attributes_manager.session_attributes = {}
        
        respuestas = [
            "Ups, algo no salió como esperaba. ¿Podemos intentarlo de nuevo?",
            "Perdón, tuve un pequeño problema. ¿Lo intentamos otra vez?",
            "Disculpa, hubo un inconveniente. ¿Qué querías hacer?"
        ]
        
        return (
            handler_input.response_builder
                .speak(random.choice(respuestas))
                .ask("¿En qué puedo ayudarte?")
                .response
        )

# ==============================
# Registrar handlers - ORDEN CRÍTICO
# ==============================
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(MostrarOpcionesIntentHandler())

# ContinuarAgregarHandler DEBE ir ANTES que otros handlers para interceptar respuestas
sb.add_request_handler(ContinuarAgregarHandler())

# Luego AgregarLibroIntentHandler
sb.add_request_handler(AgregarLibroIntentHandler())

# Luego los demás handlers
sb.add_request_handler(ListarLibrosIntentHandler())
sb.add_request_handler(BuscarLibroIntentHandler())
sb.add_request_handler(PrestarLibroIntentHandler())
sb.add_request_handler(DevolverLibroIntentHandler())
sb.add_request_handler(ConsultarPrestamosIntentHandler())
sb.add_request_handler(ConsultarDevueltosIntentHandler())
sb.add_request_handler(LimpiarCacheIntentHandler())
sb.add_request_handler(SiguientePaginaIntentHandler())
sb.add_request_handler(SalirListadoIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
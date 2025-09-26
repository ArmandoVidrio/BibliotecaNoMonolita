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
# Handlers
# ==============================

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
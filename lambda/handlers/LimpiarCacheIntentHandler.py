import ask_sdk_core.utils as ask_utils
import logging
from ask_sdk_core.dispatch_components import AbstractRequestHandler

from helpers.utils import get_random_phrase, sincronizar_estados_libros
from enums import ALGO_MAS, PREGUNTAS_QUE_HACER
from datasources.DataPersistency import DatabaseManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

from database import _CACHE

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
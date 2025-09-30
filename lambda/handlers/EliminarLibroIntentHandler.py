import logging
import ask_sdk_core.utils as ask_utils
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from database.database import DatabaseManager
from utility.utils import get_random_phrase
from constants.constants import PREGUNTAS_QUE_HACER, ALGO_MAS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class EliminarLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("EliminarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            session_attrs = handler_input.attributes_manager.session_attributes

            logger.info(f"EliminarLibro - Título pedido: {titulo}")

            # Recuperar valores de sesión si existen
            if session_attrs.get("eliminando_libro"):
                titulo = titulo or session_attrs.get("titulo_eliminar_temp")

            # Pedir título si no viene
            if not titulo:
                session_attrs["eliminando_libro"] = True
                session_attrs["esperando"] = "titulo_eliminar"
                return (
                    handler_input.response_builder
                        .speak("Entiendo. ¿Cuál es el título del libro que quieres eliminar?")
                        .ask("¿Qué libro deseas eliminar?")
                        .response
                )

            # Guardar temporalmente en sesión
            session_attrs["titulo_eliminar_temp"] = titulo
            session_attrs["eliminando_libro"] = True

            # Buscar y eliminar
            user_data = DatabaseManager.get_user_data(handler_input)
            libros = user_data.get("libros_disponibles", [])

            encontrado = None
            for libro in libros:
                if libro.get("titulo", "").strip().lower() == titulo.strip().lower():
                    encontrado = libro
                    break

            if not encontrado:
                # Limpiar sesión
                handler_input.attributes_manager.session_attributes = {}
                speak = f"No encontré ningún libro con el título '{titulo}'. " + get_random_phrase(ALGO_MAS)
                return (
                    handler_input.response_builder
                        .speak(speak)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )

            # Remover libro
            libros = [l for l in libros if l.get("id") != encontrado.get("id")]
            user_data["libros_disponibles"] = libros

            # Actualizar estadísticas
            stats = user_data.setdefault("estadisticas", {})
            stats["total_libros"] = len(libros)

            DatabaseManager.save_user_data(handler_input, user_data)

            # Limpiar sesión
            handler_input.attributes_manager.session_attributes = {}

            speak_output = f"Listo. Eliminé '{encontrado.get('titulo')}'. Ahora tienes {len(libros)} libros en tu biblioteca. "
            speak_output += get_random_phrase(ALGO_MAS)

            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )

        except Exception as e:
            logger.error(f"Error en EliminarLibro: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema eliminando el libro. Intentemos de nuevo.")
                    .ask("¿Qué libro quieres eliminar?")
                    .response
            )

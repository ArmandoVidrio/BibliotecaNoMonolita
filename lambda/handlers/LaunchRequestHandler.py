from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

from helpers.utils import sincronizar_estados_libros
from datetime import datetime
import logging

from datasources.DataPersistency import DatabaseManager
from constants import SALUDOS, OPCIONES_MENU, PREGUNTAS_QUE_HACER
from helpers.utils import get_random_phrase

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
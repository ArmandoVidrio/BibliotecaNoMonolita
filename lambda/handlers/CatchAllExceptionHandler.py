import logging
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
import random

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
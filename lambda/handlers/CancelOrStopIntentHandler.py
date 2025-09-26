from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils
import random

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
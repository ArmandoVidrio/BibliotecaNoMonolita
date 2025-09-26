import logging
from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

# Asegúrate de tener acceso al handler que maneja la lista de libros
from handlers.ListarLibrosIntentHandler import ListarLibrosIntentHandler

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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
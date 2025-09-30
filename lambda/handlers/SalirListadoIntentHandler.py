import ask_sdk_core.utils as ask_utils
from ask_sdk_core.dispatch_components import AbstractRequestHandler

from utility.utils import get_random_phrase
from constants.constants import ALGO_MAS, PREGUNTAS_QUE_HACER

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
from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

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
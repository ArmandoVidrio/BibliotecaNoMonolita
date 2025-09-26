from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # Limpiar sesión
        handler_input.attributes_manager.session_attributes = {}
        return handler_input.response_builder.response
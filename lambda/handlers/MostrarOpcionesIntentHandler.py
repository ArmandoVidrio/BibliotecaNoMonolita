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
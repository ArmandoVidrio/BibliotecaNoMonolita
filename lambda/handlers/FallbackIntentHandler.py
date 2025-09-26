from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils
from datetime import datetime
import random

from datasources.DataPersistency import DatabaseManager
from helpers.utils import generar_id_unico, get_random_phrase
from enums import ALGO_MAS, PREGUNTAS_QUE_HACER

class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        session_attrs = handler_input.attributes_manager.session_attributes
        
        # Si estamos agregando un libro, manejar las respuestas
        if session_attrs.get("agregando_libro"):
            paso_actual = session_attrs.get("paso_actual")
            
            # Intentar obtener el texto del usuario del request
            request = handler_input.request_envelope.request
            
            # Para el fallback, Alexa a veces incluye el texto en el intent name o en slots genéricos
            # Vamos a asumir que el usuario respondió correctamente
            
            if paso_actual == "titulo":
                # El usuario probablemente dijo el título pero Alexa no lo reconoció
                return (
                    handler_input.response_builder
                        .speak("No entendí bien el título. ¿Puedes repetirlo más despacio?")
                        .ask("¿Cuál es el título del libro?")
                        .response
                )
            
            elif paso_actual == "autor":
                # Asumimos que dijo "no sé" o un nombre no reconocido
                session_attrs["autor_temp"] = "Desconocido"
                session_attrs["paso_actual"] = "tipo"
                titulo = session_attrs.get("titulo_temp")
                
                return (
                    handler_input.response_builder
                        .speak(f"De acuerdo, continuemos con '{titulo}'. ¿De qué tipo o género es? Por ejemplo: novela, fantasía, historia. Si no sabes, di: no sé.")
                        .ask("¿De qué tipo es el libro?")
                        .response
                )
            
            elif paso_actual == "tipo":
                # Asumimos que dijo "no sé" o un tipo no reconocido
                titulo_final = session_attrs.get("titulo_temp")
                autor_final = session_attrs.get("autor_temp", "Desconocido")
                tipo_final = "Sin categoría"
                
                # Guardar el libro
                user_data = DatabaseManager.get_user_data(handler_input)
                libros = user_data.get("libros_disponibles", [])
                
                # Verificar duplicado
                for libro in libros:
                    if libro.get("titulo", "").lower() == titulo_final.lower():
                        handler_input.attributes_manager.session_attributes = {}
                        return (
                            handler_input.response_builder
                                .speak(f"'{titulo_final}' ya está en tu biblioteca. " + get_random_phrase(ALGO_MAS))
                                .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                                .response
                        )
                
                nuevo_libro = {
                    "id": generar_id_unico(),
                    "titulo": titulo_final,
                    "autor": autor_final,
                    "tipo": tipo_final,
                    "fecha_agregado": datetime.now().isoformat(),
                    "total_prestamos": 0,
                    "estado": "disponible"
                }
                
                libros.append(nuevo_libro)
                user_data["libros_disponibles"] = libros
                
                # Actualizar estadísticas
                stats = user_data.setdefault("estadisticas", {})
                stats["total_libros"] = len(libros)
                
                DatabaseManager.save_user_data(handler_input, user_data)
                
                # Limpiar sesión
                handler_input.attributes_manager.session_attributes = {}
                
                speak_output = f"¡Perfecto! He agregado '{titulo_final}'"
                if autor_final != "Desconocido":
                    speak_output += f" de {autor_final}"
                speak_output += f". Ahora tienes {len(libros)} libros en tu biblioteca. "
                speak_output += get_random_phrase(ALGO_MAS)
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
        
        # Si estamos listando libros con paginación
        if session_attrs.get("listando_libros"):
            speak_output = "No entendí eso. ¿Quieres ver más libros? Di 'siguiente' para continuar o 'salir' para terminar."
            ask_output = "Di 'siguiente' o 'salir'."
        else:
            # Comportamiento normal del fallback
            respuestas = [
                "Disculpa, no entendí eso. ¿Podrías repetirlo de otra forma?",
                "Hmm, no estoy seguro de qué quisiste decir. ¿Me lo puedes decir de otra manera?",
                "Perdón, no comprendí. ¿Puedes intentarlo de nuevo?"
            ]
            
            speak_output = random.choice(respuestas)
            speak_output += " Recuerda que puedo ayudarte a agregar libros, listarlos, prestarlos o registrar devoluciones."
            ask_output = "¿Qué te gustaría hacer?"
        
        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(ask_output)
                .response
        )
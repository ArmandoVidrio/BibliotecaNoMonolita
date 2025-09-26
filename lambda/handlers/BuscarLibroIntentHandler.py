import logging
from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

from helpers.database import DatabaseManager
from helpers.utils import get_random_phrase, sincronizar_estados_libros, buscar_libro_por_titulo
from helpers.frases import ALGO_MAS, PREGUNTAS_QUE_HACER

class BuscarLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("BuscarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            
            if not titulo:
                return (
                    handler_input.response_builder
                        .speak("¿Qué libro quieres buscar?")
                        .ask("Dime el título del libro que buscas.")
                        .response
                )
            
            user_data = DatabaseManager.get_user_data(handler_input)
            user_data = sincronizar_estados_libros(user_data)
            libros = user_data.get("libros_disponibles", [])
            
            libros_encontrados = buscar_libro_por_titulo(libros, titulo)
            
            if not libros_encontrados:
                speak_output = f"No encontré ningún libro con el título '{titulo}' en tu biblioteca. "
                speak_output += get_random_phrase(ALGO_MAS)
            elif len(libros_encontrados) == 1:
                libro = libros_encontrados[0]
                speak_output = f"Encontré '{libro['titulo']}'. "
                speak_output += f"Autor: {libro.get('autor', 'Desconocido')}. "
                speak_output += f"Tipo: {libro.get('tipo', 'Sin categoría')}. "
                speak_output += f"Estado: {libro.get('estado', 'disponible')}. "
                
                if libro.get('total_prestamos', 0) > 0:
                    speak_output += f"Ha sido prestado {libro['total_prestamos']} veces. "
                
                speak_output += get_random_phrase(ALGO_MAS)
            else:
                speak_output = f"Encontré {len(libros_encontrados)} libros que coinciden con '{titulo}': "
                for libro in libros_encontrados[:3]:
                    speak_output += f"'{libro['titulo']}' de {libro.get('autor', 'Desconocido')}, "
                speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
            
        except Exception as e:
            logger.error(f"Error en BuscarLibro: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema buscando el libro. ¿Intentamos de nuevo?")
                    .ask("¿Qué libro buscas?")
                    .response
            )
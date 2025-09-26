import logging
from datetime import datetime
from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

from helpers.database import DatabaseManager
from helpers.utils import generar_id_unico, get_random_phrase
from helpers.frases import ALGO_MAS, PREGUNTAS_QUE_HACER

class AgregarLibroIntentHandler(AbstractRequestHandler):
    """Handler para agregar libros"""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AgregarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            autor = ask_utils.get_slot_value(handler_input, "autor")
            tipo = ask_utils.get_slot_value(handler_input, "tipo")
            
            session_attrs = handler_input.attributes_manager.session_attributes
            
            logger.info(f"AgregarLibro - Título: {titulo}, Autor: {autor}, Tipo: {tipo}")
            logger.info(f"Session: {session_attrs}")
            
            # Recuperar valores de sesión si existen
            if session_attrs.get("agregando_libro"):
                titulo = titulo or session_attrs.get("titulo_temp")
                autor = autor or session_attrs.get("autor_temp")
                tipo = tipo or session_attrs.get("tipo_temp")
            
            # PASO 1: Pedir título
            if not titulo:
                session_attrs["agregando_libro"] = True
                session_attrs["esperando"] = "titulo"
                return (
                    handler_input.response_builder
                        .speak("¡Perfecto! Vamos a agregar un libro. ¿Cuál es el título?")
                        .ask("¿Cuál es el título del libro?")
                        .response
                )
            
            # Guardar título
            session_attrs["titulo_temp"] = titulo
            session_attrs["agregando_libro"] = True
            
            # PASO 2: Pedir autor
            if not autor:
                session_attrs["esperando"] = "autor"
                return (
                    handler_input.response_builder
                        .speak(f"¡'{titulo}' suena interesante! ¿Quién es el autor? Si no lo sabes, di: no sé.")
                        .ask("¿Quién es el autor?")
                        .response
                )
            
            # Guardar autor
            session_attrs["autor_temp"] = autor
            
            # PASO 3: Pedir tipo
            if not tipo:
                session_attrs["esperando"] = "tipo"
                autor_text = f" de {autor}" if autor and autor.lower() not in ["no sé", "no se"] else ""
                return (
                    handler_input.response_builder
                        .speak(f"Casi listo con '{titulo}'{autor_text}. ¿De qué tipo o género es? Si no sabes, di: no sé.")
                        .ask("¿De qué tipo es el libro?")
                        .response
                )
            
            # Normalizar valores
            if autor and autor.lower() in ["no sé", "no se", "no lo sé"]:
                autor = "Desconocido"
            if tipo and tipo.lower() in ["no sé", "no se", "no lo sé"]:
                tipo = "Sin categoría"
            
            # Guardar el libro
            user_data = DatabaseManager.get_user_data(handler_input)
            libros = user_data.get("libros_disponibles", [])
            
            # Verificar duplicado
            for libro in libros:
                if libro.get("titulo", "").lower() == titulo.lower():
                    handler_input.attributes_manager.session_attributes = {}
                    return (
                        handler_input.response_builder
                            .speak(f"'{titulo}' ya está en tu biblioteca. " + get_random_phrase(ALGO_MAS))
                            .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                            .response
                    )
            
            nuevo_libro = {
                "id": generar_id_unico(),
                "titulo": titulo,
                "autor": autor if autor else "Desconocido",
                "tipo": tipo if tipo else "Sin categoría",
                "fecha_agregado": datetime.now().isoformat(),
                "total_prestamos": 0,
                "estado": "disponible"
            }
            
            libros.append(nuevo_libro)
            user_data["libros_disponibles"] = libros
            
            stats = user_data.setdefault("estadisticas", {})
            stats["total_libros"] = len(libros)
            
            DatabaseManager.save_user_data(handler_input, user_data)
            
            # Limpiar sesión
            handler_input.attributes_manager.session_attributes = {}
            
            speak_output = f"¡Perfecto! He agregado '{titulo}'"
            if autor and autor != "Desconocido":
                speak_output += f" de {autor}"
            if tipo and tipo != "Sin categoría":
                speak_output += f", categoría {tipo}"
            speak_output += f". Ahora tienes {len(libros)} libros en tu biblioteca. "
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )

        except Exception as e:
            logger.error(f"Error en AgregarLibro: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema agregando el libro. Intentemos de nuevo.")
                    .ask("¿Qué libro quieres agregar?")
                    .response
            )
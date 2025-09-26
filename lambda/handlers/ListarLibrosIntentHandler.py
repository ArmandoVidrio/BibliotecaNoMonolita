import ask_sdk_core.utils as ask_utils
import logging
from ask_sdk_core.dispatch_components import AbstractRequestHandler

from datasources.DataPersistency import DatabaseManager
from helpers.utils import get_random_phrase, buscar_libros_por_autor, sincronizar_estados_libros
from enums import ALGO_MAS, PREGUNTAS_QUE_HACER, LIBROS_POR_PAGINA

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ListarLibrosIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ListarLibrosIntent")(handler_input)

    def handle(self, handler_input):
        try:
            # Obtener parámetros de filtrado
            filtro = ask_utils.get_slot_value(handler_input, "filtro_tipo")
            autor = ask_utils.get_slot_value(handler_input, "autor")
            
            user_data = DatabaseManager.get_user_data(handler_input)
            
            # IMPORTANTE: Sincronizar estados antes de listar
            user_data = sincronizar_estados_libros(user_data)
            DatabaseManager.save_user_data(handler_input, user_data)
            
            session_attrs = handler_input.attributes_manager.session_attributes
            
            todos_libros = user_data.get("libros_disponibles", [])
            prestamos = user_data.get("prestamos_activos", [])
            
            if not todos_libros:
                speak_output = "Aún no tienes libros en tu biblioteca. ¿Te gustaría agregar el primero? Solo di: agrega un libro."
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Quieres agregar tu primer libro?")
                        .response
                )
            
            # Filtrar libros según el criterio
            libros_filtrados = todos_libros.copy()
            titulo_filtro = ""
            
            if autor:
                libros_filtrados = buscar_libros_por_autor(libros_filtrados, autor)
                titulo_filtro = f" de {autor}"
            elif filtro:
                if filtro.lower() in ["prestados", "prestado"]:
                    ids_prestados = [p.get("libro_id") for p in prestamos]
                    libros_filtrados = [l for l in libros_filtrados if l.get("id") in ids_prestados]
                    titulo_filtro = " prestados"
                elif filtro.lower() in ["disponibles", "disponible"]:
                    ids_prestados = [p.get("libro_id") for p in prestamos]
                    libros_filtrados = [l for l in libros_filtrados if l.get("id") not in ids_prestados]
                    titulo_filtro = " disponibles"
            
            if not libros_filtrados:
                speak_output = f"No encontré libros{titulo_filtro}. " + get_random_phrase(ALGO_MAS)
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
            
            # Paginación
            pagina_actual = session_attrs.get("pagina_libros", 0)
            inicio = pagina_actual * LIBROS_POR_PAGINA
            fin = min(inicio + LIBROS_POR_PAGINA, len(libros_filtrados))
            
            # Si son 10 o menos, listar todos
            if len(libros_filtrados) <= LIBROS_POR_PAGINA:
                speak_output = f"Tienes {len(libros_filtrados)} libros{titulo_filtro}: "
                titulos = [f"'{l.get('titulo', 'Sin título')}'" for l in libros_filtrados]
                speak_output += ", ".join(titulos) + ". "
                speak_output += get_random_phrase(ALGO_MAS)
                
                # Limpiar paginación
                session_attrs["pagina_libros"] = 0
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                        .response
                )
            
            # Si son más de 10, paginar
            libros_pagina = libros_filtrados[inicio:fin]
            
            if pagina_actual == 0:
                speak_output = f"Tienes {len(libros_filtrados)} libros{titulo_filtro}. "
                speak_output += f"Te los voy a mostrar de {LIBROS_POR_PAGINA} en {LIBROS_POR_PAGINA}. "
            else:
                speak_output = f"Página {pagina_actual + 1}. "
            
            speak_output += f"Libros del {inicio + 1} al {fin}: "
            titulos = [f"'{l.get('titulo', 'Sin título')}'" for l in libros_pagina]
            speak_output += ", ".join(titulos) + ". "
            
            if fin < len(libros_filtrados):
                speak_output += f"Quedan {len(libros_filtrados) - fin} libros más. Di 'siguiente' para continuar o 'salir' para terminar."
                session_attrs["pagina_libros"] = pagina_actual + 1
                session_attrs["listando_libros"] = True
                session_attrs["libros_filtrados"] = libros_filtrados
                ask_output = "¿Quieres ver más libros? Di 'siguiente' o 'salir'."
            else:
                speak_output += "Esos son todos los libros. " + get_random_phrase(ALGO_MAS)
                session_attrs["pagina_libros"] = 0
                session_attrs["listando_libros"] = False
                ask_output = get_random_phrase(PREGUNTAS_QUE_HACER)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(ask_output)
                    .response
            )
            
        except Exception as e:
            logger.error(f"Error en ListarLibros: {e}", exc_info=True)
            handler_input.attributes_manager.session_attributes = {}
            return (
                handler_input.response_builder
                    .speak("Hubo un problema consultando tu biblioteca. ¿Intentamos de nuevo?")
                    .ask("¿Qué te gustaría hacer?")
                    .response
            )
import logging
import ask_sdk_core.utils as ask_utils
import random
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from datetime import datetime, timedelta

from datasources.DataPersistency import DatabaseManager
from helpers.utils import get_random_phrase, generar_id_unico, generar_id_prestamo, buscar_libro_por_titulo_exacto, sincronizar_estados_libros
from enums import CONFIRMACIONES, ALGO_MAS, PREGUNTAS_QUE_HACER

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class PrestarLibroIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("PrestarLibroIntent")(handler_input)

    def handle(self, handler_input):
        try:
            titulo = ask_utils.get_slot_value(handler_input, "titulo")
            nombre_persona = ask_utils.get_slot_value(handler_input, "nombre_persona")

            if not titulo:
                prompts = [
                    "¡Claro! ¿Qué libro quieres prestar?",
                    "Por supuesto. ¿Cuál libro vas a prestar?",
                    "¡Perfecto! ¿Qué libro necesitas prestar?"
                ]
                return (
                    handler_input.response_builder
                        .speak(random.choice(prompts))
                        .ask("¿Cuál es el título del libro?")
                        .response
                )

            user_data = DatabaseManager.get_user_data(handler_input)
            
            # IMPORTANTE: Sincronizar estados antes de prestar
            user_data = sincronizar_estados_libros(user_data)
            
            libros = user_data.get("libros_disponibles", [])
            prestamos = user_data.get("prestamos_activos", [])

            # Buscar el libro específico
            libro = buscar_libro_por_titulo_exacto(libros, titulo)
            
            if not libro:
                speak_output = f"Hmm, no encuentro '{titulo}' en tu biblioteca. "
                if libros:
                    # Mostrar solo libros disponibles (no prestados)
                    ids_prestados = [p.get("libro_id") for p in prestamos]
                    disponibles = [l for l in libros if l.get("id") not in ids_prestados]
                    if disponibles:
                        ejemplos = [l.get("titulo") for l in disponibles[:2]]
                        speak_output += f"Tienes disponibles: {', '.join(ejemplos)}. ¿Cuál quieres prestar?"
                    else:
                        speak_output += "Todos tus libros están prestados actualmente."
                else:
                    speak_output += "De hecho, aún no tienes libros en tu biblioteca."
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Qué libro quieres prestar?")
                        .response
                )

            # Verificar que el libro tiene ID
            if not libro.get("id"):
                libro["id"] = generar_id_unico()
                # Actualizar el libro en la lista
                for idx, l in enumerate(libros):
                    if l.get("titulo") == libro.get("titulo"):
                        libros[idx]["id"] = libro["id"]
                        break

            # Verificar si ESTE libro específico ya está prestado
            libro_ya_prestado = False
            prestamo_existente = None
            for p in prestamos:
                if p.get("libro_id") == libro.get("id"):
                    libro_ya_prestado = True
                    prestamo_existente = p
                    break

            if libro_ya_prestado:
                speak_output = f"'{libro['titulo']}' ya está prestado a {prestamo_existente.get('persona', 'alguien')}. "
                # Sugerir otros libros disponibles
                ids_prestados = [p.get("libro_id") for p in prestamos]
                disponibles = [l for l in libros if l.get("id") not in ids_prestados]
                if disponibles:
                    speak_output += "¿Quieres prestar otro libro? "
                    ejemplos = [l.get("titulo") for l in disponibles[:2]]
                    speak_output += f"Tienes disponibles: {', '.join(ejemplos)}."
                else:
                    speak_output += "No tienes más libros disponibles para prestar."
                
                return (
                    handler_input.response_builder
                        .speak(speak_output)
                        .ask("¿Qué otro libro quieres prestar?")
                        .response
                )

            # Crear préstamo
            prestamo = {
                "id": generar_id_prestamo(),
                "libro_id": libro["id"],
                "titulo": libro["titulo"],
                "persona": nombre_persona if nombre_persona else "un amigo",
                "fecha_prestamo": datetime.now().isoformat(),
                "fecha_limite": (datetime.now() + timedelta(days=7)).isoformat(),
                "estado": "activo"
            }

            prestamos.append(prestamo)
            user_data["prestamos_activos"] = prestamos
            
            # Marcar el libro como prestado
            for l in libros:
                if l.get("id") == libro.get("id"):
                    l["estado"] = "prestado"
                    l["total_prestamos"] = l.get("total_prestamos", 0) + 1
                    break

            stats = user_data.get("estadisticas", {})
            stats["total_prestamos"] = stats.get("total_prestamos", 0) + 1

            DatabaseManager.save_user_data(handler_input, user_data)

            # Respuesta natural
            confirmacion = get_random_phrase(CONFIRMACIONES)
            persona_text = f" a {nombre_persona}" if nombre_persona else ""
            fecha_limite = datetime.fromisoformat(prestamo['fecha_limite']).strftime("%d de %B")
            
            speak_output = f"{confirmacion} He registrado el préstamo de '{libro['titulo']}'{persona_text}. "
            speak_output += f"La fecha de devolución es el {fecha_limite}. "
            
            # Informar cuántos libros disponibles quedan
            ids_prestados = [p.get("libro_id") for p in prestamos]
            disponibles = len([l for l in libros if l.get("id") not in ids_prestados])
            if disponibles > 0:
                speak_output += f"Te quedan {disponibles} libros disponibles. "
            else:
                speak_output += "Ya no tienes más libros disponibles para prestar. "
            
            speak_output += get_random_phrase(ALGO_MAS)

            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en PrestarLibro: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Ups, tuve un problema registrando el préstamo. ¿Lo intentamos de nuevo?")
                    .ask("¿Qué libro quieres prestar?")
                    .response
            )
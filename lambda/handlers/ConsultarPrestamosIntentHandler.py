import logging
from datetime import datetime
from ask_sdk_core.dispatch_components import AbstractRequestHandler
import ask_sdk_core.utils as ask_utils

from datasources.DataPersistency import DatabaseManager
from helpers.utils import get_random_phrase, sincronizar_estados_libros
from enums import ALGO_MAS, PREGUNTAS_QUE_HACER

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ConsultarPrestamosIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ConsultarPrestamosIntent")(handler_input)

    def handle(self, handler_input):
        try:
            user_data = DatabaseManager.get_user_data(handler_input)
            user_data = sincronizar_estados_libros(user_data)
            prestamos = user_data.get("prestamos_activos", [])
            
            if not prestamos:
                speak_output = "¡Excelente! No tienes ningún libro prestado en este momento. Todos están en su lugar. "
                speak_output += get_random_phrase(ALGO_MAS)
            else:
                # Introducción variada
                if len(prestamos) == 1:
                    speak_output = "Déjame ver... Solo tienes un libro prestado: "
                else:
                    speak_output = f"Déjame revisar... Tienes {len(prestamos)} libros prestados: "
                
                # Listar préstamos con detalles
                detalles = []
                hay_vencidos = False
                hay_proximos = False
                
                for p in prestamos[:5]:
                    detalle = f"'{p['titulo']}' está con {p.get('persona', 'alguien')}"
                    
                    # Calcular días restantes
                    fecha_limite = datetime.fromisoformat(p['fecha_limite'])
                    dias_restantes = (fecha_limite - datetime.now()).days
                    
                    if dias_restantes < 0:
                        detalle += " (¡ya venció!)"
                        hay_vencidos = True
                    elif dias_restantes == 0:
                        detalle += " (vence hoy)"
                        hay_proximos = True
                    elif dias_restantes <= 2:
                        detalle += f" (vence en {dias_restantes} días)"
                        hay_proximos = True
                    
                    detalles.append(detalle)
                
                speak_output += "; ".join(detalles) + ". "
                
                if len(prestamos) > 5:
                    speak_output += f"Y {len(prestamos) - 5} más. "
                
                # Agregar advertencias si es necesario
                if hay_vencidos:
                    speak_output += "Te sugiero pedir la devolución de los libros vencidos. "
                elif hay_proximos:
                    speak_output += "Algunos están por vencer, ¡no lo olvides! "
                
                speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en ConsultarPrestamos: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema consultando los préstamos. ¿Intentamos de nuevo?")
                    .ask("¿Qué más deseas hacer?")
                    .response
            )
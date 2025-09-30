import os
import json
import logging
from datetime import datetime, timedelta
import random
import uuid

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_model import Response, DialogState
from ask_sdk_model.dialog import ElicitSlotDirective, DelegateDirective
from ask_sdk_s3.adapter import S3Adapter
import boto3
from botocore.exceptions import ClientError
from database.database import DatabaseManager
from utility.utils import sincronizar_estados_libros, get_random_phrase, generar_id_unico, buscar_libro_por_titulo, buscar_libro_por_titulo_exacto, buscar_libros_por_autor, generar_id_prestamo
from constants.constants import SALUDOS, OPCIONES_MENU, PREGUNTAS_QUE_HACER, ALGO_MAS, CONFIRMACIONES
from configuration.configurations import LIBROS_POR_PAGINA

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ConsultarDevueltosIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ConsultarDevueltosIntent")(handler_input)

    def handle(self, handler_input):
        try:
            user_data = DatabaseManager.get_user_data(handler_input)
            historial = user_data.get("historial_prestamos", [])
            
            if not historial:
                speak_output = "Aún no has registrado devoluciones. Cuando prestes libros y te los devuelvan, aparecerán aquí. "
            else:
                total = len(historial)
                speak_output = f"Has registrado {total} "
                speak_output += "devolución en total. " if total == 1 else "devoluciones en total. "
                
                # Mostrar TODOS los títulos (o hasta un máximo razonable)
                if total <= 10:
                    speak_output += "Los libros devueltos son: "
                    detalles = []
                    for h in historial:
                        detalle = f"'{h.get('titulo', 'Sin título')}'"
                        if h.get('persona') and h['persona'] not in ['Alguien', 'un amigo']:
                            detalle += f" que prestaste a {h['persona']}"
                        detalles.append(detalle)
                    speak_output += ", ".join(detalles) + ". "
                else:
                    # Si son muchos, mostrar los últimos 5
                    recientes = historial[-5:]
                    speak_output += "Los 5 más recientes son: "
                    detalles = []
                    for h in reversed(recientes):
                        detalle = f"'{h.get('titulo', 'Sin título')}'"
                        if h.get('persona') and h['persona'] not in ['Alguien', 'un amigo']:
                            detalle += f" a {h['persona']}"
                        detalles.append(detalle)
                    speak_output += ", ".join(detalles) + ". "
            
            speak_output += get_random_phrase(ALGO_MAS)
            
            return (
                handler_input.response_builder
                    .speak(speak_output)
                    .ask(get_random_phrase(PREGUNTAS_QUE_HACER))
                    .response
            )
        except Exception as e:
            logger.error(f"Error en ConsultarDevueltos: {e}", exc_info=True)
            return (
                handler_input.response_builder
                    .speak("Hubo un problema consultando el historial.")
                    .ask("¿Qué más deseas hacer?")
                    .response
            )

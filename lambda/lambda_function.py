import os
import json
import logging
import random
import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_model import Response, DialogState
from ask_sdk_model.dialog import ElicitSlotDirective, DelegateDirective
from ask_sdk_s3.adapter import S3Adapter

from handlers.LaunchRequestHandler import LaunchRequestHandler
from handlers.MostrarOpcionesIntentHandler import MostrarOpcionesIntentHandler
from handlers.ContinuarAgregarHandler import ContinuarAgregarHandler
from handlers.AgregarLibroIntentHandler import AgregarLibroIntentHandler
from handlers.ListarLibrosIntentHandler import ListarLibrosIntentHandler
from handlers.BuscarLibroIntentHandler import BuscarLibroIntentHandler
from handlers.PrestarLibroIntentHandler import PrestarLibroIntentHandler
from handlers.DevolverLibroIntentHandler import DevolverLibroIntentHandler
from handlers.ConsultarPrestamosIntentHandler import ConsultarPrestamosIntentHandler
from handlers.ConsultarDevueltosIntentHandler import ConsultarDevueltosIntentHandler
from handlers.LimpiarCacheIntentHandler import LimpiarCacheIntentHandler
from handlers.SiguientePaginaIntentHandler import SiguientePaginaIntentHandler
from handlers.SalirListadoIntentHandler import SalirListadoIntentHandler
from handlers.HelpIntentHandler import HelpIntentHandler
from handlers.CancelOrStopIntentHandler import CancelOrStopIntentHandler
from handlers.FallbackIntentHandler import FallbackIntentHandler
from handlers.SessionEndedRequestHandler import SessionEndedRequestHandler
from handlers.CatchAllExceptionHandler import CatchAllExceptionHandler

# ==============================
# Registrar handlers - ORDEN CRÍTICO
# ==============================
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(MostrarOpcionesIntentHandler())

# ContinuarAgregarHandler DEBE ir ANTES que otros handlers para interceptar respuestas
sb.add_request_handler(ContinuarAgregarHandler())

# Luego AgregarLibroIntentHandler
sb.add_request_handler(AgregarLibroIntentHandler())

# Luego los demás handlers
sb.add_request_handler(ListarLibrosIntentHandler())
sb.add_request_handler(BuscarLibroIntentHandler())
sb.add_request_handler(PrestarLibroIntentHandler())
sb.add_request_handler(DevolverLibroIntentHandler())
sb.add_request_handler(ConsultarPrestamosIntentHandler())
sb.add_request_handler(ConsultarDevueltosIntentHandler())
sb.add_request_handler(LimpiarCacheIntentHandler())
sb.add_request_handler(SiguientePaginaIntentHandler())
sb.add_request_handler(SalirListadoIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
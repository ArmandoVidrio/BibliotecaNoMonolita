import os
import logging
import boto3
from botocore.exceptions import ClientError

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

from configuration.AppConfiguration import USE_FAKE_S3
from datasources.DataPersistency import FakeS3Adapter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ==============================
# Inicializar persistence adapter
# ==============================
if USE_FAKE_S3:
    persistence_adapter = FakeS3Adapter()
else:
    s3_bucket = os.environ.get("S3_PERSISTENCE_BUCKET")
    if not s3_bucket:
        raise RuntimeError("S3_PERSISTENCE_BUCKET es requerido cuando USE_FAKE_S3=false")
    logger.info(f"🪣 Usando S3Adapter con bucket: {s3_bucket}")
    persistence_adapter = S3Adapter(bucket_name=s3_bucket)

sb = CustomSkillBuilder(persistence_adapter=persistence_adapter)

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
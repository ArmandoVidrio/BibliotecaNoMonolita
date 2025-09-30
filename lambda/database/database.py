import logging
import os
import boto3
from datetime import datetime, timedelta
from ask_sdk_s3.adapter import S3Adapter
from ask_sdk_core.skill_builder import CustomSkillBuilder

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

USE_FAKE_S3 = os.getenv("USE_FAKE_S3", "false").lower() == "true"
ENABLE_DDB_CACHE = os.getenv("ENABLE_DDB_CACHE", "false").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
LIBROS_POR_PAGINA = 10

# ==============================
# Adaptador de "Fake S3" (memoria)
# ==============================
_FAKE_STORE = {}

class FakeS3Adapter:
    def __init__(self):
        logger.info("🧪 Usando FakeS3Adapter (memoria)")

    @staticmethod
    def _user_id_from_envelope(request_envelope):
        return request_envelope.context.system.user.user_id

    def get_attributes(self, request_envelope):
        uid = self._user_id_from_envelope(request_envelope)
        return _FAKE_STORE.get(uid, {})

    def save_attributes(self, request_envelope, attributes):
        uid = self._user_id_from_envelope(request_envelope)
        _FAKE_STORE[uid] = attributes or {}
        logger.info(f"FakeS3Adapter: guardados atributos para {uid}")

    def delete_attributes(self, request_envelope):
        uid = self._user_id_from_envelope(request_envelope)
        if uid in _FAKE_STORE:
            del _FAKE_STORE[uid]
            logger.info(f"FakeS3Adapter: atributos borrados para {uid}")

# ==============================
# Cache en memoria con TTL
# ==============================
_CACHE = {}

def _cache_get(user_id, cache=_CACHE, now_fn=datetime.now):
    item = cache.get(user_id)
    if not item:
        return None
    if now_fn().timestamp() > item["expire_at"]:
        cache.pop(user_id, None)
        return None
    return item["data"]

def _cache_put(user_id, data, cache=_CACHE, ttl_seconds=CACHE_TTL_SECONDS, now_fn=datetime.now):
    cache[user_id] = {
        "data": data,
        "expire_at": (now_fn() + timedelta(seconds=ttl_seconds)).timestamp()
    }


class _DatabaseManagerImpl:
    DDB_TABLE = "BibliotecaSkillCache"

    def __init__(self, enable_ddb_cache=ENABLE_DDB_CACHE, cache_ttl_seconds=CACHE_TTL_SECONDS):
        self.enable_ddb_cache = enable_ddb_cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache = _CACHE

        self._dynamodb = None
        if self.enable_ddb_cache:
            try:
                import boto3
                self._dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
            except Exception as e:
                logger.warning(f"No se pudo inicializar DynamoDB resource: {e}")
                self._dynamodb = None

    def _user_id(self, handler_input):
        return handler_input.request_envelope.context.system.user.user_id

    def _get_ddb_table(self):
        if not self.enable_ddb_cache or not self._dynamodb:
            return None
        try:
            table = self._dynamodb.Table(self.DDB_TABLE)
            table.load()
            return table
        except Exception as e:
            logger.warning(f"DDB deshabilitado o sin permisos: {e}")
            return None

    def get_user_data(self, handler_input):
        user_id = self._user_id(handler_input)

        # 1) Cache en memoria
        data = _cache_get(user_id)
        if data is not None:
            logger.info("⚡ Cache hit (memoria)")
            return data

        # 2) Cache en DDB (opcional)
        if self.enable_ddb_cache:
            try:
                table = self._get_ddb_table()
                if table:
                    resp = table.get_item(Key={"user_id": user_id})
                    if "Item" in resp:
                        data = resp["Item"].get("data", {})
                        logger.info("⚡ Cache hit (DynamoDB)")
                        _cache_put(user_id, data, cache=self._cache, ttl_seconds=self.cache_ttl_seconds)
                        return data
            except Exception as e:
                logger.warning(f"DDB get_item error: {e}")

        # 3) Persistencia principal
        attr_mgr = handler_input.attributes_manager
        persistent = attr_mgr.persistent_attributes
        if not persistent:
            persistent = self.initial_data()
            attr_mgr.persistent_attributes = persistent
            attr_mgr.save_persistent_attributes()

        # 4) Actualizar caches
        _cache_put(user_id, persistent, cache=self._cache, ttl_seconds=self.cache_ttl_seconds)
        if self.enable_ddb_cache:
            try:
                table = self._get_ddb_table()
                if table:
                    table.put_item(Item={
                        "user_id": user_id,
                        "data": persistent,
                        "ttl": int((datetime.now() + timedelta(seconds=self.cache_ttl_seconds)).timestamp())
                    })
            except Exception as e:
                logger.warning(f"DDB put_item error: {e}")

        return persistent

    def save_user_data(self, handler_input, data):
        user_id = self._user_id(handler_input)

        # Persistencia principal
        attr_mgr = handler_input.attributes_manager
        attr_mgr.persistent_attributes = data
        attr_mgr.save_persistent_attributes()

        _cache_put(user_id, data, cache=self._cache, ttl_seconds=self.cache_ttl_seconds)

        if self.enable_ddb_cache:
            try:
                table = self._get_ddb_table()
                if table:
                    table.put_item(Item={
                        "user_id": user_id,
                        "data": data,
                        "ttl": int((datetime.now() + timedelta(seconds=self.cache_ttl_seconds)).timestamp())
                    })
            except Exception as e:
                logger.warning(f"DDB put_item error: {e}")

    def initial_data(self):
        return {
            "libros_disponibles": [],
            "prestamos_activos": [],
            "historial_prestamos": [],
            "estadisticas": {
                "total_libros": 0,
                "total_prestamos": 0,
                "total_devoluciones": 0
            },
            "historial_conversaciones": [],
            "configuracion": {"limite_prestamos": 10, "dias_prestamo": 7},
            "usuario_frecuente": False
        }

    # Operaciones para handlers
    def clear_cache_for_user(self, handler_input):
        user_id = self._user_id(handler_input)
        self.clear_cache_by_user_id(user_id)

    def clear_cache_by_user_id(self, user_id):
        if user_id in self._cache:
            del self._cache[user_id]

DatabaseManager = _DatabaseManagerImpl()

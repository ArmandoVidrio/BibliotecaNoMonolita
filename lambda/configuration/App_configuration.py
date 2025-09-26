# ==============================
# Feature flags & configuración
# ==============================
USE_FAKE_S3 = os.getenv("USE_FAKE_S3", "false").lower() == "true"
ENABLE_DDB_CACHE = os.getenv("ENABLE_DDB_CACHE", "false").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
LIBROS_POR_PAGINA = 10
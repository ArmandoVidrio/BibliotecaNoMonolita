# ==============================
# Cache en memoria con TTL
# ==============================
_CACHE = {}

def _cache_get(user_id):
    item = _CACHE.get(user_id)
    if not item:
        return None
    if datetime.now().timestamp() > item["expire_at"]:
        _CACHE.pop(user_id, None)
        return None
    return item["data"]

def _cache_put(user_id, data):
    _CACHE[user_id] = {
        "data": data,
        "expire_at": (datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS)).timestamp()
    }

dynamodb = boto3.resource("dynamodb", region_name="us-east-1") if ENABLE_DDB_CACHE else None
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING

COLECCION_PRESENCIA = "user_presence"
VENTANA_ACTIVO_SEGUNDOS = 120
RETENCION_SEGUNDOS = 30 * 24 * 60 * 60


def inicializar_indices_presencia(db) -> None:
    presencia = db[COLECCION_PRESENCIA]
    presencia.create_index(
        [("lastSeen", ASCENDING)],
        expireAfterSeconds=RETENCION_SEGUNDOS,
        name="ttl_user_presence_last_seen",
    )


def registrar_actividad(db, user: dict) -> dict:
    ahora = datetime.now(timezone.utc)
    user_id = str(user.get("_id") or "")
    if not user_id:
        raise ValueError("USER_ID_REQUIRED")
    db[COLECCION_PRESENCIA].update_one(
        {"_id": user_id},
        {
            "$set": {
                "lastSeen": ahora,
                "role": str(user.get("role") or "customer"),
            },
            "$setOnInsert": {"createdAt": ahora},
        },
        upsert=True,
    )
    return {
        "active": True,
        "lastSeen": ahora.isoformat(),
        "activeWindowSeconds": VENTANA_ACTIVO_SEGUNDOS,
    }


def obtener_usuarios_activos(db) -> dict:
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(seconds=VENTANA_ACTIVO_SEGUNDOS)
    cantidad = db[COLECCION_PRESENCIA].count_documents(
        {"lastSeen": {"$gte": limite}, "role": "customer"}
    )
    return {
        "activeUsers": cantidad,
        "measuredAt": ahora.isoformat(),
        "activeWindowSeconds": VENTANA_ACTIVO_SEGUNDOS,
    }

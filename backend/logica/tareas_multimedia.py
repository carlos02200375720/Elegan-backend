from datetime import datetime, timedelta, timezone
from uuid import uuid4

from pymongo import ASCENDING, ReturnDocument


COLECCION_TAREAS_MULTIMEDIA = "media_tasks"
MAX_INTENTOS = 4
DURACION_LEASE = timedelta(minutes=15)


def inicializar_indices_tareas_multimedia(db) -> None:
    tareas = db[COLECCION_TAREAS_MULTIMEDIA]
    tareas.create_index(
        [("status", ASCENDING), ("nextAttemptAt", ASCENDING), ("createdAt", ASCENDING)],
        name="idx_media_tasks_pending",
    )
    tareas.create_index(
        [("leaseUntil", ASCENDING)],
        name="idx_media_tasks_lease",
    )


def encolar_procesamiento_video(db, object_name: str, content_type: str) -> str:
    task_id = str(uuid4())
    ahora = datetime.now(timezone.utc)
    db[COLECCION_TAREAS_MULTIMEDIA].insert_one({
        "_id": task_id,
        "type": "prepare_video",
        "objectName": object_name,
        "contentType": content_type,
        "status": "pending",
        "attempts": 0,
        "maxAttempts": MAX_INTENTOS,
        "createdAt": ahora,
        "updatedAt": ahora,
    })
    return task_id


def encolar_limpieza_multimedia(db, referencias: set[str] | list[str]) -> str | None:
    valores = sorted({str(item).strip() for item in referencias if str(item).strip()})
    if not valores:
        return None
    task_id = str(uuid4())
    ahora = datetime.now(timezone.utc)
    db[COLECCION_TAREAS_MULTIMEDIA].insert_one({
        "_id": task_id,
        "type": "cleanup_media",
        "references": valores,
        "status": "pending",
        "attempts": 0,
        "maxAttempts": MAX_INTENTOS,
        "createdAt": ahora,
        "updatedAt": ahora,
    })
    return task_id


def _reclamar_tarea(db):
    ahora = datetime.now(timezone.utc)
    return db[COLECCION_TAREAS_MULTIMEDIA].find_one_and_update(
        {"$or": [
            {"status": "pending"},
            {"status": "retry", "nextAttemptAt": {"$lte": ahora}},
            {"status": "processing", "leaseUntil": {"$lte": ahora}},
        ]},
        {"$set": {
            "status": "processing",
            "startedAt": ahora,
            "updatedAt": ahora,
            "leaseUntil": ahora + DURACION_LEASE,
        }, "$inc": {"attempts": 1}},
        sort=[("createdAt", ASCENDING), ("_id", ASCENDING)],
        return_document=ReturnDocument.AFTER,
    )


def _ejecutar_tarea(db, tarea: dict) -> None:
    tipo = tarea.get("type")
    if tipo == "prepare_video":
        from backend.logica.media import preparar_video_gcs
        preparar_video_gcs(
            tarea["objectName"],
            tarea.get("contentType") or "video/mp4",
        )
        return
    if tipo == "cleanup_media":
        from backend.logica.media import eliminar_referencias_multimedia_sin_uso
        eliminar_referencias_multimedia_sin_uso(db, tarea.get("references") or [])
        return
    raise ValueError("UNKNOWN_MEDIA_TASK_TYPE")


def procesar_tareas_multimedia(db, max_tasks: int = 1) -> int:
    """Procesa una cantidad acotada de tareas después de responder al cliente."""
    completadas = 0
    tareas = db[COLECCION_TAREAS_MULTIMEDIA]
    for _ in range(max(1, min(int(max_tasks), 20))):
        tarea = _reclamar_tarea(db)
        if tarea is None:
            break
        try:
            _ejecutar_tarea(db, tarea)
            ahora = datetime.now(timezone.utc)
            tareas.update_one(
                {"_id": tarea["_id"], "status": "processing"},
                {"$set": {
                    "status": "completed",
                    "completedAt": ahora,
                    "updatedAt": ahora,
                    "leaseUntil": None,
                }, "$unset": {"lastError": "", "nextAttemptAt": ""}},
            )
            completadas += 1
        except Exception as error:
            ahora = datetime.now(timezone.utc)
            agotada = int(tarea.get("attempts", 1)) >= int(tarea.get("maxAttempts", MAX_INTENTOS))
            espera = min(300, 15 * (2 ** max(0, int(tarea.get("attempts", 1)) - 1)))
            cambios = {
                "status": "failed" if agotada else "retry",
                "updatedAt": ahora,
                "leaseUntil": None,
                "lastError": str(error)[:500],
            }
            if not agotada:
                cambios["nextAttemptAt"] = ahora + timedelta(seconds=espera)
            tareas.update_one(
                {"_id": tarea["_id"], "status": "processing"},
                {"$set": cambios},
            )
    return completadas

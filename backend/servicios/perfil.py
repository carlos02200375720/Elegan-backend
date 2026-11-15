from datetime import datetime, timezone
from typing import Any

from pymongo.collection import Collection

NOMBRE_COLECCION_PERFILES = "profiles"
CAMPOS_PROTEGIDOS = {"_id", "userId", "role", "createdAt", "updatedAt"}


def coleccion_perfiles(db: Any) -> Collection:
    return db[NOMBRE_COLECCION_PERFILES]


def inicializar_indices_perfiles(db: Any) -> None:
    coleccion_perfiles(db).create_index(
        [("userId", 1)],
        unique=True,
        name="idx_profiles_user_id_unique",
    )


def formatear_perfil(documento: dict | None, user: dict) -> dict:
    if not documento:
        return {
            "userId": str(user.get("_id") or user.get("id") or ""),
            "displayName": user.get("name") or "",
            "email": user.get("email") or "",
        }

    perfil = dict(documento)
    identificador = perfil.pop("_id", None)
    if identificador is not None:
        perfil["id"] = str(identificador)
    return perfil


def obtener_perfil(db: Any, user: dict) -> dict:
    documento = coleccion_perfiles(db).find_one(
        {"userId": str(user["_id"])}
    )
    return {"item": formatear_perfil(documento, user)}


def actualizar_perfil(db: Any, user: dict, datos: dict) -> dict:
    ahora = datetime.now(timezone.utc)
    datos_limpios = {
        campo: valor
        for campo, valor in datos.items()
        if campo not in CAMPOS_PROTEGIDOS
    }
    user_id = str(user["_id"])

    coleccion_perfiles(db).update_one(
        {"userId": user_id},
        {
            "$set": {
                **datos_limpios,
                "userId": user_id,
                "updatedAt": ahora,
            },
            "$setOnInsert": {"createdAt": ahora},
        },
        upsert=True,
    )
    return {"success": True}

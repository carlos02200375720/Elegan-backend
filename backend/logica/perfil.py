from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pymongo.collection import Collection

CAMPOS_PROTEGIDOS = {"_id", "userId", "role", "createdAt", "updatedAt"}
CAMPOS_PERFIL_CLIENTE = {"name", "email", "phone", "address", "city"}


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
    documento = db["super-admins"].find_one(
        {"_id": str(user["_id"])}
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

    db["super-admins"].update_one(
        {"_id": user_id},
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


def obtener_perfil_cliente(db: Any, user: dict) -> dict:
    documento = db["users"].find_one(
        {"_id": str(user["_id"])},
        {"passwordHash": 0},
    )
    if not documento:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    return {
        "item": {
            "userId": str(documento["_id"]),
            "displayName": documento.get("name", ""),
            "name": documento.get("name", ""),
            "email": documento.get("email", ""),
            "phone": documento.get("phone", ""),
            "address": documento.get("address", ""),
            "city": documento.get("city", ""),
            "updatedAt": documento.get("updatedAt"),
        }
    }


def actualizar_perfil_cliente(db: Any, user: dict, datos: dict) -> dict:
    user_id = str(user["_id"])
    datos_limpios = {
        campo: valor
        for campo, valor in datos.items()
        if campo in CAMPOS_PERFIL_CLIENTE and valor is not None
    }

    if "email" in datos_limpios:
        email = str(datos_limpios["email"]).strip().lower()
        existente = db["users"].find_one(
            {"email": email, "_id": {"$ne": user_id}},
            {"_id": 1},
        )
        admin_existente = db["super-admins"].find_one(
            {"email": email},
            {"_id": 1},
        )
        if existente or admin_existente:
            raise HTTPException(status_code=409, detail="EMAIL_ALREADY_REGISTERED")
        datos_limpios["email"] = email

    if not datos_limpios:
        raise HTTPException(status_code=400, detail="EMPTY_PROFILE_UPDATE")

    datos_limpios["updatedAt"] = datetime.now(timezone.utc)
    resultado = db["users"].update_one(
        {"_id": user_id},
        {"$set": datos_limpios},
    )
    if resultado.matched_count != 1:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")

    actualizado = db["users"].find_one(
        {"_id": user_id},
        {"passwordHash": 0},
    )
    return {
        "success": True,
        "item": {
            "userId": user_id,
            "displayName": actualizado.get("name", ""),
            "name": actualizado.get("name", ""),
            "email": actualizado.get("email", ""),
            "phone": actualizado.get("phone", ""),
            "address": actualizado.get("address", ""),
            "city": actualizado.get("city", ""),
            "updatedAt": actualizado.get("updatedAt"),
        },
    }

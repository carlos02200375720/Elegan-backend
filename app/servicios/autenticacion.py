import hmac
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pymongo.collection import Collection

from app.configuracion import settings

EMISOR = "elegan-movil-api"
AUDIENCIA_MOVIL = "elegan-android"
AUDIENCIA_ADMIN = "elegan-admin"
PATRON_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def colecciones(db: Any) -> tuple[Collection, Collection]:
    return db["users"], db["super-admins"]


def correo_normalizado(email: str) -> str:
    return email.strip().lower()


def validar_configuracion_jwt() -> str:
    secret = settings.jwt_secret
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="AUTH_NOT_CONFIGURED")
    return secret


def crear_token(user: dict, cliente: str) -> str:
    secret = validar_configuracion_jwt()
    audience = AUDIENCIA_ADMIN if cliente == "admin" else AUDIENCIA_MOVIL
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["_id"]),
        "role": user.get("role", "customer"),
        "iss": EMISOR,
        "aud": audience,
        "iat": ahora,
        "exp": ahora + timedelta(days=7),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def usuario_publico(user: dict) -> dict:
    result = {
        "id": str(user.get("_id", "")),
        "email": user.get("email"),
        "name": user.get("name", ""),
        "photoUrl": user.get("photoUrl", ""),
        "role": user.get("role", "customer"),
        "provider": user.get("provider", "password"),
        "createdAt": user.get("createdAt"),
    }
    if result["role"] in ("admin", "superadmin"):
        result["permissions"] = user.get("permissions", ["all"])
    else:
        result["sharedPublications"] = user.get("sharedPublications", [])
    return result


def buscar_usuario(db: Any, user_id: str) -> dict | None:
    users, admins = colecciones(db)
    return users.find_one({"_id": user_id}) or admins.find_one({"_id": user_id})


def verificar_token(token: str, db: Any) -> dict:
    try:
        payload = jwt.decode(
            token,
            validar_configuracion_jwt(),
            algorithms=["HS256"],
            issuer=EMISOR,
            audience=[AUDIENCIA_MOVIL, AUDIENCIA_ADMIN],
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="SESSION_EXPIRED")
    except (jwt.InvalidTokenError, HTTPException):
        raise HTTPException(status_code=401, detail="INVALID_SESSION")

    user = buscar_usuario(db, str(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="USER_NOT_FOUND")
    if user.get("isActive") is False:
        raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")
    if user.get("role") != payload.get("role"):
        raise HTTPException(status_code=401, detail="INVALID_SESSION")
    return user


def validar_acceso_admin(user: dict) -> None:
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")


def hash_contrasena(password: str) -> str:
    # bcrypt procesa hasta 72 bytes; se conserva la compatibilidad con bcryptjs.
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verificar_contrasena(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def registrar_cliente(db: Any, email: str, password: str, name: str, cliente: str) -> dict:
    if cliente == "admin":
        raise HTTPException(status_code=403, detail="ADMIN_REGISTRATION_DISABLED")
    email = correo_normalizado(email)
    if not PATRON_CORREO.match(email):
        raise HTTPException(status_code=400, detail="INVALID_EMAIL")
    if len(password) < 8 or len(password) > 128:
        raise HTTPException(status_code=400, detail="PASSWORD_REQUIREMENTS")
    name = name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="INVALID_NAME")

    users, admins = colecciones(db)
    if admins.find_one({"email": email}) or users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="EMAIL_ALREADY_REGISTERED")

    now = datetime.now(timezone.utc)
    user = {
        "_id": str(uuid.uuid4()),
        "email": email,
        "name": name,
        "passwordHash": hash_contrasena(password),
        "photoUrl": "",
        "role": "customer",
        "provider": "password",
        "sharedPublications": [],
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        users.insert_one(user)
    except Exception as error:
        if getattr(error, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="EMAIL_ALREADY_REGISTERED")
        raise
    return user


def iniciar_sesion(db: Any, email: str, password: str, cliente: str) -> dict:
    email = correo_normalizado(email)
    users, admins = colecciones(db)
    user = admins.find_one({"email": email}) or users.find_one({"email": email})
    if not user or not verificar_contrasena(password, user.get("passwordHash")):
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")
    if user.get("isActive") is False:
        raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")
    if cliente == "admin":
        validar_acceso_admin(user)
    return user


def iniciar_sesion_google(db: Any, id_token: str, cliente: str) -> dict:
    if not settings.google_web_client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_SIGN_IN_NOT_CONFIGURED")
    try:
        payload = google_id_token.verify_oauth2_token(
            id_token, google_requests.Request(), settings.google_web_client_id
        )
    except Exception:
        raise HTTPException(status_code=401, detail="GOOGLE_AUTH_FAILED")

    google_sub = payload.get("sub")
    email = correo_normalizado(str(payload.get("email", "")))
    if not google_sub or not email or payload.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="INVALID_GOOGLE_IDENTITY")

    users, admins = colecciones(db)
    admin_email = correo_normalizado(settings.super_admin_email) if settings.super_admin_email else ""
    es_superadmin = bool(admin_email) and hmac.compare_digest(email, admin_email)

    if es_superadmin:
        admin = admins.find_one({"googleSub": google_sub}) or admins.find_one({"email": email})
        now = datetime.now(timezone.utc)
        if admin:
            if admin.get("isActive") is False:
                raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")
            update = {
                "googleSub": google_sub,
                "email": email,
                "photoUrl": payload.get("picture") or admin.get("photoUrl", ""),
                "updatedAt": now,
            }
            admins.update_one({"_id": admin["_id"]}, {"$set": update})
            admin.update(update)
        else:
            admin = {
                "_id": str(uuid.uuid4()),
                "email": email,
                "name": payload.get("name") or "Super Administrador",
                "photoUrl": payload.get("picture", ""),
                "googleSub": google_sub,
                "role": "superadmin",
                "provider": "google",
                "permissions": ["all"],
                "isActive": True,
                "createdAt": now,
                "updatedAt": now,
            }
            admins.insert_one(admin)
        # No se borra ni mueve ningún documento de users durante el acceso.
        return admin

    if cliente == "admin":
        raise HTTPException(status_code=403, detail="ADMIN_REQUIRED")

    user = users.find_one({"email": email})
    if user:
        if user.get("isActive") is False:
            raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")
        users.update_one({"_id": user["_id"]}, {"$set": {"updatedAt": datetime.now(timezone.utc)}})
    else:
        now = datetime.now(timezone.utc)
        user = {
            "_id": str(uuid.uuid4()),
            "email": email,
            "name": payload.get("name", ""),
            "photoUrl": payload.get("picture", ""),
            "role": "customer",
            "provider": "google",
            "sharedPublications": [],
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            users.insert_one(user)
        except Exception as error:
            if getattr(error, "code", None) == 11000:
                user = users.find_one({"email": email})
            else:
                raise
    return user

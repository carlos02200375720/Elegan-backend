import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import HTTPException

from backend.configuracion import settings
from backend.logica.autenticacion import hash_contrasena


COLECCION = "recuperacion_contrasenas"


def _configurar_correo() -> None:
    if not all((settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.smtp_from_email)):
        raise HTTPException(status_code=503, detail="PASSWORD_RESET_EMAIL_NOT_CONFIGURED")


def _enviar_codigo(destinatario: str, codigo: str) -> None:
    mensaje = EmailMessage()
    mensaje["Subject"] = "Código para recuperar tu contraseña de Elegan"
    mensaje["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    mensaje["To"] = destinatario
    mensaje.set_content(
        f"Recibimos una solicitud para restablecer la contraseña de tu cuenta Elegan.\n\n"
        f"Tu código es: {codigo}\n\n"
        "El código vence en 15 minutos. Si no solicitaste este cambio, ignora este correo."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as servidor:
            servidor.starttls()
            servidor.login(settings.smtp_username, settings.smtp_password)
            servidor.send_message(mensaje)
    except Exception as error:
        raise HTTPException(status_code=503, detail="PASSWORD_RESET_EMAIL_UNAVAILABLE") from error


def solicitar_codigo_recuperacion(db, email: str) -> dict:
    _configurar_correo()
    correo = email.strip().lower()
    usuario = db["usuarios"].find_one(
        {"email": correo, "provider": "password", "isActive": {"$ne": False}},
        {"_id": 1},
    )
    respuesta = {
        "success": True,
        "message": "Si existe una cuenta con ese correo y contraseña, recibirás un código."
    }
    if not usuario:
        return respuesta

    ahora = datetime.now(timezone.utc)
    tokens = db[COLECCION]
    tokens.create_index("expiresAt", expireAfterSeconds=0, name="idx_password_reset_expiry")
    tokens.create_index("email", unique=True, name="idx_password_reset_email_unique")
    existente = tokens.find_one({"email": correo})
    if existente and existente.get("createdAt") and existente["createdAt"] > ahora - timedelta(minutes=1):
        return respuesta

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    tokens.update_one(
        {"email": correo},
        {"$set": {
            "email": correo,
            "userId": str(usuario["_id"]),
            "codeHash": hashlib.sha256(codigo.encode("utf-8")).hexdigest(),
            "createdAt": ahora,
            "expiresAt": ahora + timedelta(minutes=15),
            "attempts": 0,
        }},
        upsert=True,
    )
    _enviar_codigo(correo, codigo)
    return respuesta


def restablecer_contrasena(db, email: str, codigo: str, nueva_contrasena: str) -> dict:
    correo = email.strip().lower()
    tokens = db[COLECCION]
    registro = tokens.find_one({"email": correo})
    ahora = datetime.now(timezone.utc)
    if not registro or registro.get("expiresAt") <= ahora or registro.get("attempts", 0) >= 5:
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_RESET_CODE")

    hash_codigo = hashlib.sha256(codigo.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(hash_codigo, registro.get("codeHash", "")):
        tokens.update_one({"_id": registro["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_RESET_CODE")

    resultado = db["usuarios"].update_one(
        {"_id": registro["userId"], "email": correo, "provider": "password"},
        {"$set": {
            "passwordHash": hash_contrasena(nueva_contrasena),
            "updatedAt": ahora,
        }},
    )
    if resultado.matched_count != 1:
        tokens.delete_one({"_id": registro["_id"]})
        raise HTTPException(status_code=400, detail="INVALID_OR_EXPIRED_RESET_CODE")

    tokens.delete_one({"_id": registro["_id"]})
    return {"success": True, "message": "La contraseña se actualizó correctamente."}

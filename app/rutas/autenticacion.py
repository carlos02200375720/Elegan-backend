from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.esquemas.autenticacion import GoogleEntrada, InicioSesionEntrada, RegistroEntrada
from app.servicios.autenticacion import (
    crear_token,
    iniciar_sesion,
    iniciar_sesion_google,
    registrar_cliente,
    usuario_publico,
    validar_acceso_admin,
    verificar_token,
)

router_movil = APIRouter(prefix="/api/movil/auth", tags=["Autenticación móvil"])
router_admin = APIRouter(prefix="/api/admin/auth", tags=["Autenticación administrativa"])


def obtener_db(request: Request):
    db = getattr(request.app.state, "mongodb", None)
    if db is None:
        raise HTTPException(status_code=503, detail="DATABASE_NOT_CONFIGURED")
    return db


def usuario_actual(authorization: str | None = Header(default=None), db=Depends(obtener_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    return verificar_token(authorization[7:].strip(), db)


def respuesta_autenticacion(user: dict, cliente: Literal["movil", "admin"]):
    if cliente == "admin":
        validar_acceso_admin(user)
    return {"token": crear_token(user, cliente), "user": usuario_publico(user)}


@router_movil.post("/register", status_code=status.HTTP_201_CREATED)
def registrar(datos: RegistroEntrada, db=Depends(obtener_db)):
    user = registrar_cliente(db, str(datos.email), datos.password, datos.name, "movil")
    return respuesta_autenticacion(user, "movil")


@router_movil.post("/login")
def login(datos: InicioSesionEntrada, db=Depends(obtener_db)):
    user = iniciar_sesion(db, str(datos.email), datos.password, "movil")
    return respuesta_autenticacion(user, "movil")


@router_movil.post("/google")
def login_google(datos: GoogleEntrada, db=Depends(obtener_db)):
    user = iniciar_sesion_google(db, datos.idToken, "movil")
    return respuesta_autenticacion(user, "movil")


@router_movil.get("/me")
def mi_cuenta(user=Depends(usuario_actual)):
    return {"user": usuario_publico(user)}


@router_movil.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router_admin.post("/login")
def login_admin(datos: InicioSesionEntrada, db=Depends(obtener_db)):
    user = iniciar_sesion(db, str(datos.email), datos.password, "admin")
    return respuesta_autenticacion(user, "admin")


@router_admin.post("/google")
def login_google_admin(datos: GoogleEntrada, db=Depends(obtener_db)):
    user = iniciar_sesion_google(db, datos.idToken, "admin")
    return respuesta_autenticacion(user, "admin")


@router_admin.get("/me")
def mi_cuenta_admin(user=Depends(usuario_actual)):
    validar_acceso_admin(user)
    return {"user": usuario_publico(user)}


@router_admin.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_admin():
    return Response(status_code=status.HTTP_204_NO_CONTENT)

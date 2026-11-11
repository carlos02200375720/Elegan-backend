# Elegan-backend

Backend central de Elegan, desarrollado en Python con FastAPI y preparado para Google Cloud Run.

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

En Windows PowerShell: `.venv\\Scripts\\Activate.ps1`.

## Endpoints del sistema

- `GET /`: estado básico del servicio.
- `GET /health`: comprobación básica de que la API responde.
- `/docs`: documentación OpenAPI.

## Autenticación móvil

- `POST /api/movil/auth/register`: registro de cliente por correo y contraseña.
- `POST /api/movil/auth/login`: inicio de sesión.
- `POST /api/movil/auth/google`: inicio de sesión con Google ID token.
- `GET /api/movil/auth/me`: devuelve la cuenta asociada al JWT.
- `POST /api/movil/auth/logout`: respuesta 204; el cliente descarta su JWT.

## Autenticación administrativa

- `POST /api/admin/auth/login`: inicio de sesión de cuentas con rol `admin` o `superadmin`.
- `POST /api/admin/auth/google`: inicio de sesión Google del superadministrador autorizado.
- `GET /api/admin/auth/me`: valida sesión y rol administrativo.
- `POST /api/admin/auth/logout`: respuesta 204.

El registro público solo crea documentos en `users` con rol `customer`. Las cuentas administrativas se consultan exclusivamente en `super-admins`; no se promueve un cliente automáticamente ni se elimina/mueve ningún documento entre colecciones durante el inicio de sesión.

## Variables de entorno

Configura `MONGODB_URI`, `MONGODB_DATABASE`, `JWT_SECRET` (mínimo 32 caracteres), `GOOGLE_WEB_CLIENT_ID` y `SUPER_ADMIN_EMAIL`. `GCS_BUCKET_NAME` se reserva para la integración de multimedia. Copia `.env.example` a `.env` en desarrollo local y no subas secretos al repositorio.

## JWT

Los tokens duran siete días y conservan el emisor `elegan-movil-api`. Los tokens móviles usan la audiencia `elegan-android`; los administrativos usan `elegan-admin`. Las rutas protegidas vuelven a consultar la cuenta en MongoDB y verifican su estado y rol.

## MongoDB y Google Cloud Storage

MongoDB usa las colecciones existentes `users` y `super-admins`. La integración de GCS utiliza Application Default Credentials; en Cloud Run se debe asignar una cuenta de servicio con permisos mínimos sobre el bucket.

## Separación de clientes

- `/api/movil/...`: aplicación móvil.
- `/api/admin/...`: panel administrativo.

Esta implementación es la primera migración de autenticación. Debe probarse con una copia de prueba de MongoDB y credenciales OAuth configuradas antes de cambiar producción. No reemplaza todavía el backend anterior.

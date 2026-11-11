# Elegan-backend

Backend central de Elegan, desarrollado en Python con FastAPI y preparado para Google Cloud Run.

## Desarrollo local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

En Windows PowerShell: `.venv\Scripts\Activate.ps1`.

## Endpoints iniciales

- `GET /`: estado básico del servicio.
- `GET /health`: comprobación básica de que la API responde.
- `/docs`: documentación OpenAPI.

## MongoDB

Configura `MONGODB_URI` y `MONGODB_DATABASE` mediante variables de entorno. El cliente se crea al iniciar la aplicación solo si existe una URI y se cierra al apagarla. La conexión de red se realiza cuando se ejecuta la primera operación de base de datos.

## Google Cloud Storage

Configura `GCS_BUCKET_NAME`. La integración usa Application Default Credentials, por lo que en Cloud Run debe asignarse al servicio una cuenta de servicio con permisos mínimos sobre el bucket. No se guardan claves JSON en el repositorio.

## Variables de entorno

Copia `.env.example` a `.env` para desarrollo local. No subas secretos al repositorio.

## Separación de clientes

- `/api/movil/...`: aplicación móvil.
- `/api/admin/...`: panel administrativo.

La migración de rutas y reglas del backend actual debe realizarse por módulos y validarse antes de cambiar producción. Este scaffold no sustituye todavía al backend en producción.

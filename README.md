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

## Endpoints iniciales
- `GET /`: estado básico.
- `GET /health`: comprobación de salud.
- `/docs`: documentación OpenAPI.

## Servicios
MongoDB para persistencia y Google Cloud Storage para multimedia.

## Separación de clientes
- `/api/movil/...`: aplicación móvil.
- `/api/admin/...`: panel administrativo.

La migración de las rutas y reglas del backend actual debe realizarse por módulos y validarse antes de cambiar producción. No guardar secretos en el repositorio.

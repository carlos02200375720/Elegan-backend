import re
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from google.api_core.exceptions import GoogleAPIError
from google.cloud import storage

from app.configuracion import settings


TIPOS_PERMITIDOS = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/webm", "video/quicktime",
}
TAMANO_MAXIMO = 100 * 1024 * 1024
TAMANO_BLOQUE = 8 * 1024 * 1024


def guardar_multimedia(
    archivo: UploadFile, nombre: str | None = None, prefijo: str = "movil"
) -> dict:
    if not archivo:
        raise HTTPException(status_code=400, detail="FILE_REQUIRED")

    content_type = (archivo.content_type or "").lower()
    if content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(status_code=415, detail="UNSUPPORTED_MEDIA_TYPE")
    if not settings.gcs_bucket_name:
        raise HTTPException(status_code=503, detail="MEDIA_STORAGE_NOT_CONFIGURED")
    if archivo.size is not None and archivo.size > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")

    nombre_original = nombre or archivo.filename or "media"
    nombre_seguro = re.sub(r"[^a-zA-Z0-9._-]", "_", nombre_original)[:180] or "media"
    object_name = (
        f"{prefijo}/{int(datetime.now(timezone.utc).timestamp() * 1000)}-"
        f"{uuid4()}-{nombre_seguro}"
    )
    objeto = None
    tamano = 0

    try:
        cliente = storage.Client()
        bucket = cliente.bucket(settings.gcs_bucket_name)
        objeto = bucket.blob(object_name)
        objeto.cache_control = "public, max-age=31536000"
        objeto.content_type = content_type

        # UploadFile usa almacenamiento temporal de Starlette; se copia a GCS
        # en bloques para no cargar el archivo completo en memoria.
        with objeto.open("wb", chunk_size=TAMANO_BLOQUE) as destino:
            while True:
                bloque = archivo.file.read(TAMANO_BLOQUE)
                if not bloque:
                    break
                tamano += len(bloque)
                if tamano > TAMANO_MAXIMO:
                    raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
                destino.write(bloque)

        url = (
            f"https://storage.googleapis.com/{settings.gcs_bucket_name}/"
            f"{quote(object_name, safe='/-_.')}"
        )
        return {
            "url": url,
            "objectName": object_name,
            "contentType": content_type,
            "size": tamano,
        }
    except HTTPException:
        if objeto is not None and tamano > TAMANO_MAXIMO:
            try:
                objeto.delete()
            except Exception:
                pass
        raise
    except GoogleAPIError as error:
        raise HTTPException(status_code=502, detail="MEDIA_STORAGE_ERROR") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="MEDIA_UPLOAD_FAILED") from error

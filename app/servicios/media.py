import re
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from google.api_core.exceptions import GoogleAPIError, NotFound
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


# Campos multimedia que pueden contener URLs u objectName de GCS.
_CAMPOS_MULTIMEDIA = {
    "imageUrl", "images", "videoUrl", "videoPoster", "url",
    "mediaUrl", "mediaUrls", "objectName", "media", "files",
}


def _referencias_multimedia(documento: dict) -> set[str]:
    referencias: set[str] = set()

    def recorrer(valor, clave: str = "") -> None:
        if isinstance(valor, dict):
            for nombre, contenido in valor.items():
                if nombre in _CAMPOS_MULTIMEDIA:
                    recorrer(contenido, nombre)
                elif isinstance(contenido, (dict, list)):
                    recorrer(contenido, nombre)
        elif isinstance(valor, list):
            for elemento in valor:
                recorrer(elemento, clave)
        elif isinstance(valor, str) and clave in _CAMPOS_MULTIMEDIA:
            texto = valor.strip()
            if texto.startswith("https://storage.googleapis.com/"):
                referencias.add(texto.split("?", 1)[0])
                object_name = _object_name_desde_url(texto)
                if object_name:
                    referencias.add("object:" + object_name)
            elif clave == "objectName" and texto:
                referencias.add("object:" + texto)

    recorrer(documento)
    return referencias


def _object_name_desde_url(url: str) -> str | None:
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    prefijo = f"/{settings.gcs_bucket_name}/"
    if parsed.netloc != "storage.googleapis.com" or not parsed.path.startswith(prefijo):
        return None
    nombre = unquote(parsed.path[len(prefijo):])
    return nombre if nombre and not nombre.startswith("/") else None


def eliminar_medios_sin_referencias(db, documentos: list[dict]) -> None:
    """Elimina de GCS solo medios propios del bucket que ya no usa ningún documento."""
    candidatos: set[str] = set()
    for documento in documentos:
        candidatos.update(_referencias_multimedia(documento))

    if not candidatos:
        return

    referencias_actuales: set[str] = set()
    # Se revisan todas las colecciones para proteger medios compartidos entre
    # productos, anuncios, perfiles, pedidos u otros documentos de la aplicación.
    for nombre_coleccion in db.list_collection_names():
        for documento in db[nombre_coleccion].find({}):
            referencias_actuales.update(_referencias_multimedia(documento))

    obsoletos = candidatos - referencias_actuales
    nombres_objeto = {
        referencia[len("object:"):] if referencia.startswith("object:") else
        (_object_name_desde_url(referencia) or "")
        for referencia in obsoletos
    }
    nombres_objeto.discard("")
    if not nombres_objeto:
        return

    try:
        bucket = storage.Client().bucket(settings.gcs_bucket_name)
        for nombre_objeto in nombres_objeto:
            # Los uploads de esta API se guardan bajo estos prefijos.
            if not (nombre_objeto.startswith("movil/") or nombre_objeto.startswith("admin/")):
                continue
            try:
                bucket.blob(nombre_objeto).delete()
            except NotFound:
                # El objeto ya no existe; la limpieza ya está satisfecha.
                continue
    except GoogleAPIError as error:
        raise HTTPException(
            status_code=502, detail="MEDIA_CLEANUP_FAILED"
        ) from error

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from google.api_core.exceptions import GoogleAPIError, NotFound
from google.cloud import storage
from pymongo.errors import PyMongoError

from backend.configuracion import settings


TIPOS_PERMITIDOS = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "video/mp4", "video/webm", "video/quicktime",
}
TAMANO_MAXIMO = 100 * 1024 * 1024
TAMANO_BLOQUE = 8 * 1024 * 1024


def _preparar_mp4_para_reproduccion(archivo, directorio: str) -> str:
    """Reordena los átomos MP4 sin recodificar audio ni video."""
    ejecutable = shutil.which("ffmpeg")
    if not ejecutable:
        raise HTTPException(status_code=503, detail="MEDIA_PROCESSOR_NOT_CONFIGURED")

    entrada = os.path.join(directorio, "entrada.mp4")
    salida = os.path.join(directorio, "salida.mp4")

    total = 0
    with open(entrada, "wb") as temporal:
        while True:
            bloque = archivo.read(TAMANO_BLOQUE)
            if not bloque:
                break
            total += len(bloque)
            if total > TAMANO_MAXIMO:
                raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
            temporal.write(bloque)

    if total == 0:
        raise HTTPException(status_code=422, detail="EMPTY_VIDEO")

    try:
        resultado = subprocess.run(
            [
                ejecutable, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-y", "-i", entrada, "-map", "0", "-c", "copy",
                "-movflags", "+faststart", "-f", "mp4", salida,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=422, detail="MP4_PREPARATION_TIMEOUT") from error

    if resultado.returncode != 0 or not os.path.isfile(salida):
        raise HTTPException(status_code=422, detail="INVALID_OR_UNSUPPORTED_MP4")

    if os.path.getsize(salida) > TAMANO_MAXIMO:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")

    return salida


def guardar_multimedia(
    archivo: UploadFile, nombre: str | None = None, prefijo: str = "movil", db=None
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

        # La carga se transmite por bloques directamente a GCS. El vídeo original
        # queda disponible mientras el trabajador prepara la versión optimizada.
        with objeto.open("wb", chunk_size=TAMANO_BLOQUE) as destino:
            while True:
                bloque = archivo.file.read(TAMANO_BLOQUE)
                if not bloque:
                    break
                tamano += len(bloque)
                if tamano > TAMANO_MAXIMO:
                    raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")
                destino.write(bloque)

        if tamano == 0:
            raise HTTPException(status_code=422, detail="EMPTY_FILE")

        task_id = None
        if content_type == "video/mp4":
            if db is None:
                raise HTTPException(status_code=503, detail="MEDIA_QUEUE_NOT_CONFIGURED")
            from backend.logica.tareas_multimedia import encolar_procesamiento_video
            task_id = encolar_procesamiento_video(db, object_name, content_type)

        url = (
            f"https://storage.googleapis.com/{settings.gcs_bucket_name}/"
            f"{quote(object_name, safe='/-_.')}"
        )
        return {
            "url": url,
            "objectName": object_name,
            "contentType": content_type,
            "size": tamano,
            "processingStatus": "pending" if task_id else "not_required",
            "processingTaskId": task_id,
        }
    except HTTPException:
        if objeto is not None:
            try:
                objeto.delete()
            except Exception:
                pass
        raise
    except GoogleAPIError as error:
        if objeto is not None:
            try:
                objeto.delete()
            except Exception:
                pass
        raise HTTPException(status_code=502, detail="MEDIA_STORAGE_ERROR") from error
    except Exception as error:
        if objeto is not None:
            try:
                objeto.delete()
            except Exception:
                pass
        raise HTTPException(status_code=503, detail="MEDIA_UPLOAD_OR_QUEUE_FAILED") from error

def guardar_comprobante_privado(archivo: UploadFile, nombre: str | None = None) -> dict:
    """Guarda comprobantes en un bucket privado, separado del bucket público de catálogo."""
    if not archivo:
        raise HTTPException(status_code=400, detail="FILE_REQUIRED")
    content_type = (archivo.content_type or "").lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="PROOF_IMAGE_ONLY")
    if not settings.gcs_private_bucket_name:
        raise HTTPException(status_code=503, detail="PRIVATE_PROOF_STORAGE_NOT_CONFIGURED")
    if archivo.size is not None and archivo.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PROOF_TOO_LARGE")

    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", nombre or archivo.filename or "comprobante")[:120]
    object_name = f"comprobantes/{int(datetime.now(timezone.utc).timestamp() * 1000)}-{uuid4()}-{safe_name}"
    blob = None
    size = 0
    try:
        bucket = storage.Client().bucket(settings.gcs_private_bucket_name)
        blob = bucket.blob(object_name)
        blob.cache_control = "private, no-store, max-age=0"
        blob.content_type = content_type
        with blob.open("wb", chunk_size=TAMANO_BLOQUE) as destination:
            while True:
                chunk = archivo.file.read(TAMANO_BLOQUE)
                if not chunk:
                    break
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="PROOF_TOO_LARGE")
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="EMPTY_PROOF")
        return {"objectName": object_name, "contentType": content_type, "size": size}
    except HTTPException:
        if blob is not None:
            try:
                blob.delete()
            except Exception:
                pass
        raise
    except GoogleAPIError as error:
        if blob is not None:
            try:
                blob.delete()
            except Exception:
                pass
        raise HTTPException(status_code=502, detail="PRIVATE_PROOF_STORAGE_ERROR") from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="PRIVATE_PROOF_UPLOAD_FAILED") from error


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
    """Encola la limpieza; nunca bloquea la petición que modifica el catálogo."""
    referencias: set[str] = set()
    for documento in documentos:
        referencias.update(_referencias_multimedia(documento))
    if not referencias:
        return
    try:
        from backend.logica.tareas_multimedia import encolar_limpieza_multimedia
        encolar_limpieza_multimedia(db, referencias)
    except Exception:
        # Ante un fallo de cola se conserva el archivo. Un huérfano es preferible
        # a borrar un medio todavía utilizado o hacer fallar una edición ya guardada.
        import logging
        logging.getLogger("elegan.media").exception(
            "No se pudo encolar la limpieza multimedia; los archivos se conservan."
        )


def preparar_video_gcs(object_name: str, content_type: str = "video/mp4") -> None:
    """Prepara un MP4 en disco temporal y reemplaza el mismo objeto en GCS."""
    if not settings.gcs_bucket_name:
        raise RuntimeError("MEDIA_STORAGE_NOT_CONFIGURED")
    bucket = storage.Client().bucket(settings.gcs_bucket_name)
    objeto = bucket.blob(object_name)
    with tempfile.TemporaryDirectory(prefix="elegan-video-task-") as directorio:
        with objeto.open("rb") as fuente:
            ruta_preparada = _preparar_mp4_para_reproduccion(fuente, directorio)
        objeto.cache_control = "public, max-age=31536000"
        objeto.content_type = content_type
        objeto.upload_from_filename(
            ruta_preparada,
            content_type=content_type,
            timeout=300,
        )


def eliminar_referencias_multimedia_sin_uso(db, referencias: list[str]) -> None:
    """Elimina objetos solo después de verificar que ninguna colección los use."""
    candidatos = {str(item).strip() for item in referencias if str(item).strip()}
    if not candidatos:
        return

    urls = [item for item in candidatos if not item.startswith("object:")]
    nombres = [item[len("object:"):] for item in candidatos if item.startswith("object:")]
    campos_url = (
        "imageUrl", "videoUrl", "videoPoster", "url", "mediaUrl", "mediaUrls",
        "images", "media", "files", "images.url", "media.url", "files.url",
    )
    campos_objeto = (
        "objectName", "images.objectName", "media.objectName", "files.objectName",
    )
    condiciones = []
    if urls:
        condiciones.extend({campo: {"$in": urls}} for campo in campos_url)
    if nombres:
        condiciones.extend({campo: {"$in": nombres}} for campo in campos_objeto)
    if not condiciones:
        return
    consulta = {"$or": condiciones}

    # Si una consulta falla o excede su límite, se aborta sin borrar nada.
    try:
        for nombre_coleccion in db.list_collection_names():
            try:
                referencia = db[nombre_coleccion].find_one(
                    consulta, projection={"_id": 1}, max_time_ms=750
                )
            except PyMongoError:
                return
            if referencia is not None:
                return

        nombres_objeto = {
            item[len("object:"):] if item.startswith("object:") else
            (_object_name_desde_url(item) or "")
            for item in candidatos
        }
        nombres_objeto.discard("")
        if not nombres_objeto:
            return
        bucket = storage.Client().bucket(settings.gcs_bucket_name)
        for nombre_objeto in nombres_objeto:
            if not nombre_objeto.startswith(("movil/", "admin/", "soporte/")):
                continue
            try:
                bucket.blob(nombre_objeto).delete()
            except NotFound:
                continue
    except GoogleAPIError as error:
        raise RuntimeError("MEDIA_CLEANUP_FAILED") from error

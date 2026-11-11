from google.cloud import storage
from google.cloud.storage.bucket import Bucket

from app.configuracion import settings


def create_storage_client() -> storage.Client:
    """Usa Application Default Credentials, recomendado para Cloud Run."""
    return storage.Client()


def get_media_bucket(client: storage.Client) -> Bucket:
    if not settings.gcs_bucket_name:
        raise RuntimeError("GCS_BUCKET_NAME no está configurado.")
    return client.bucket(settings.gcs_bucket_name)

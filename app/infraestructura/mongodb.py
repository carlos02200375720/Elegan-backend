from pymongo import MongoClient
from pymongo.database import Database

from app.configuracion import settings


def create_mongodb_client() -> MongoClient | None:
    """Crea el cliente MongoDB cuando MONGODB_URI está configurada."""
    if not settings.mongodb_uri:
        return None

    return MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        appname="elegan-backend",
    )


def get_database(client: MongoClient) -> Database:
    return client[settings.mongodb_database]

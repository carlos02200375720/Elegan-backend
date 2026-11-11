from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.settings import settings

app = FastAPI(title="Elegan API", version="1.0.0", description="Backend central de Elegan.")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

@app.get("/", tags=["Sistema"])
def root():
    return {"service": "elegan-backend", "status": "running"}

@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok"}

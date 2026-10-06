from fastapi import FastAPI

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty

app = FastAPI(title="HallSpan 考场排座")
app.include_router(api_router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()


@app.get("/")
def root():
    return {"app": "hallspan", "status": "ok"}

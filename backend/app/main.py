from fastapi import FastAPI

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty

app = FastAPI(title="HallSpan 考场排座")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_empty:
        with SessionLocal() as db:
            seed_if_empty(db)


app.include_router(api_router, prefix="/api")

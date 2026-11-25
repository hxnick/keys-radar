from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from radar.api import router
from radar.config import Settings
from radar.db import make_engine
from radar.errors import register_error_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="Keys Radar",
        description="Local manual demand import and evidence lookup",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.sessions = sessionmaker(engine)
    register_error_handlers(app)
    app.include_router(router)
    return app

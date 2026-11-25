import logging

import uvicorn

from radar.config import Settings
from radar.main import create_app


def main() -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    uvicorn.run(
        create_app(settings),
        host="127.0.0.1",
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()

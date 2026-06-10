import logging.config
import os


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {
                    "format": (
                        "%(asctime)s %(levelname)s %(name)s "
                        "%(message)s"
                    ),
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": os.getenv("LOG_LEVEL", "INFO").upper(),
            },
        }
    )

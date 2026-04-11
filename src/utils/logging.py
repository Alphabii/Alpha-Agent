import sys

from loguru import logger


def setup_logging():
    """Configure loguru logging."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO",
    )
    logger.add(
        "logs/agent.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name} - {message}",
        level="DEBUG",
    )


setup_logging()

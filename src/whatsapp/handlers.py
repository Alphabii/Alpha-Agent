from loguru import logger

from src.db import get_stats
from src.whatsapp.messages import format_help, format_status


def handle_command(body: str, scanner=None) -> str:
    """Parse and handle a WhatsApp command. Returns response text."""
    cmd = body.strip().lower()
    logger.info(f"WhatsApp command: {cmd}")

    if cmd in ("status", "stats"):
        stats = get_stats()
        return format_status(stats)

    elif cmd in ("start", "resume"):
        if scanner:
            scanner.resume()
        return "▶️ Scanner resumed."

    elif cmd in ("stop", "pause"):
        if scanner:
            scanner.pause()
        return "⏸ Scanner paused."

    elif cmd == "summary":
        stats = get_stats()
        return format_status(stats)

    elif cmd in ("help", "?"):
        return format_help()

    else:
        return f"Unknown command: *{cmd}*\n\nSend *help* for available commands."

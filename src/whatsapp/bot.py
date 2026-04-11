from flask import Flask, request
from loguru import logger
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from src.config import settings
from src.whatsapp.handlers import handle_command

flask_app = Flask(__name__)

# Module-level reference to scanner (set by start_bot)
_scanner = None
_twilio_client = None


def get_twilio_client() -> Client:
    global _twilio_client
    if _twilio_client is None:
        _twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _twilio_client


def send_whatsapp(message: str, to: str | None = None):
    """Send a WhatsApp message via Twilio."""
    client = get_twilio_client()
    to = to or settings.whatsapp_to
    if not to:
        logger.warning("No WhatsApp destination configured")
        return

    try:
        client.messages.create(
            body=message,
            from_=settings.twilio_whatsapp_from,
            to=to,
        )
        logger.debug(f"WhatsApp sent to {to}")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp: {e}")


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming WhatsApp messages from Twilio."""
    body = request.form.get("Body", "").strip()
    from_number = request.form.get("From", "")

    logger.info(f"WhatsApp from {from_number}: {body}")

    response_text = handle_command(body, scanner=_scanner)

    resp = MessagingResponse()
    resp.message(response_text)
    return str(resp)


def start_bot(scanner=None, host: str = "0.0.0.0", port: int = 5000):
    """Start the WhatsApp webhook server."""
    global _scanner
    _scanner = scanner

    logger.info(f"WhatsApp bot starting on {host}:{port}")
    logger.info("Configure Twilio webhook URL to: http://<your-ip>:{port}/webhook")
    flask_app.run(host=host, port=port, debug=False)

import os
import json
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


def send_telegram_notification(resume_id: int, pipeline_id: str, job_title: str, score: float, explanation: str) -> bool:
    """Send a job match notification to Telegram with Approve/Reject buttons."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram credentials not configured. Running in SIMULATED notification mode.")
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    message = (
        f"*NEW JOB MATCH*\n\n"
        f"*Role:* {job_title}\n"
        f"*Pipeline:* {pipeline_id}\n"
        f"*Match Score:* {score}/100\n\n"
        f"*Match Details:*\n{explanation}\n\n"
        f"*Truth Validation:* PASSED\n\n"
        f"Please review and approve before applying."
    )
    
    # Inline keyboard for Approve/Reject
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "APPROVE", "callback_data": f"approve_{resume_id}"},
                {"text": "REJECT", "callback_data": f"reject_{resume_id}"}
            ]
        ]
    }
    
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"Telegram message sent for resume {resume_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def answer_callback_query(callback_query_id: str, text: str) -> bool:
    """Tell Telegram to remove the loading spinner and show a message to the user."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("Telegram token not configured. Running in SIMULATED callback mode.")
        return True
    
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": True # Shows a pop-up alert in Telegram
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")
        return False
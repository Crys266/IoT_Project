import requests
import threading
import time
import json
import os

from database import create_surveillance_db
db = create_surveillance_db()

TELEGRAM_BOT_TOKEN = "7833394325:AAFvZ-WbKkrHvTHhZ4omg4jvSrJpA9DKKgo"
CHAT_IDS_FILE = "chat_ids.json"
NOTIFICATION_COOLDOWN = 30  # seconds

last_notification = {}


def load_chat_ids():
    try:
        with open(CHAT_IDS_FILE, "r") as f:
            ids = set(json.load(f))
            print(f"[BOT] Loaded chat ids: {ids}")
            return ids
    except Exception as e:
        print(f"[BOT] No chat_ids.json or error, starting empty: {e}")
        return set()


def save_chat_ids(chat_ids):
    try:
        with open(CHAT_IDS_FILE, "w") as f:
            json.dump(list(chat_ids), f)
        print(f"[BOT] Saved chat ids: {chat_ids}")
    except Exception as e:
        print(f"[BOT] Error saving chat ids: {e}")


def register_chat_id(chat_id):
    chat_ids = load_chat_ids()
    chat_ids.add(str(chat_id))
    save_chat_ids(chat_ids)


def unregister_chat_id(chat_id):
    chat_ids = load_chat_ids()
    chat_ids.discard(str(chat_id))
    save_chat_ids(chat_ids)


def send_telegram_message(message, chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": str(chat_id),
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=data, timeout=10)
        print(f"[BOT] send_message status: {r.status_code}, resp: {r.text}")
        if r.status_code != 200:
            print(f"[BOT] Error sending message to {chat_id}: {r.text}")
    except Exception as e:
        print(f"[BOT] Telegram message error: {e}")


def send_telegram_photo(photo_path, chat_id, caption=""):
    """
    Versione migliorata per Windows - gestisce correttamente i file
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": str(chat_id),
        "caption": caption,
        "parse_mode": "HTML"
    }

    if not os.path.exists(photo_path):
        print(f"[BOT] Image not found: {photo_path}")
        return False

    try:
        # Leggi file in una volta sola
        with open(photo_path, "rb") as photo_file:
            photo_data = photo_file.read()

        print(f"[BOT] Read {len(photo_data)} bytes from {photo_path}")

        # Invia usando bytes invece di file handle
        files = {"photo": ("image.jpg", photo_data, "image/jpeg")}
        r = requests.post(url, data=data, files=files, timeout=20)

        print(f"[BOT] send_photo status: {r.status_code}")
        if r.status_code != 200:
            print(f"[BOT] Error sending photo to {chat_id}: {r.text}")
            return False
        else:
            print(f"[BOT] Photo sent successfully to {chat_id}")
            return True

    except Exception as e:
        print(f"[BOT] Telegram photo error: {e}")
        return False


def send_to_all_chats(msg, image_path=None):
    chat_ids = load_chat_ids()
    print(f"[BOT] Notifying chat_ids: {chat_ids} | msg: {msg} | img: {image_path}")

    success_count = 0
    for chat_id in chat_ids:
        try:
            if image_path:
                if send_telegram_photo(image_path, chat_id, caption=msg):
                    success_count += 1
            else:
                send_telegram_message(msg, chat_id)
                success_count += 1
        except Exception as e:
            print(f"[BOT] Error sending to {chat_id}: {e}")

    print(f"[BOT] Sent to {success_count}/{len(chat_ids)} chats")


def notify_if_danger(detection_data, gps="unknown", image_path=None, caption=None):
    """
    ✅ SIGNATURE CORRETTA - mantiene compatibilità con il codice esistente
    """
    DANGEROUS_OBJECTS = db.get_dangerous_classes()
    print(f"[BOT] notify_if_danger called with {len(detection_data)} detections, gps={gps}, image_path={image_path}")

    # Se è una chiamata manuale con caption (dalla galleria)
    if caption:
        print(f"[BOT] Manual notification with caption: {caption}")
        send_to_all_chats(caption, image_path)
        return

    # Se non ci sono detection, non fare nulla
    if not detection_data:
        print(f"[BOT] No detections to process")
        return

    now = time.time()
    for obj in detection_data:
        label = obj.get('label', '').lower()
        conf = obj.get('confidence', 0)
        print(f"[BOT] Detection: {label}, conf: {conf}")

        if label in DANGEROUS_OBJECTS and conf > 0.6:
            last_time = last_notification.get(label, 0)
            if now - last_time < NOTIFICATION_COOLDOWN:
                print(f"[BOT] Skipping notification for {label}: cooldown ({now - last_time:.1f}s ago)")
                continue

            last_notification[label] = now
            msg = (
                f"🚨 <b>Rilevato: {label.upper()}</b>\n"
                f"Confidenza: {int(conf * 100)}%\n"
                f"GPS: {gps}\n"
                f"Controlla il live!"
            )

            def send_async():
                try:
                    send_to_all_chats(msg, image_path)
                except Exception as e:
                    print(f"[BOT] Async send error: {e}")

            threading.Thread(target=send_async, daemon=True).start()
            print(f"[BOT] Notification triggered for {label} ({conf:.2f})")
        else:
            print(f"[BOT] Ignored: {label} (conf: {conf})")


# Utility for manual test
def test_bot():
    send_to_all_chats("🔔 Test messaggio manuale dal bot!", image_path=None)


if __name__ == "__main__":
    test_bot()

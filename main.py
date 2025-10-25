import sys
import io
import time
import json
import base64
import logging
import requests
import telebot
from telebot import types

# ---------- CONFIG ----------
TELEGRAM_TOKEN = "ВАШ_TELEGRAM_TOKEN"
FUSION_API_KEY = "ВАШ_FUSION_API_KEY"
FUSION_SECRET = "ВАШ_FUSION_SECRET"
FUSION_BASE_URL = "https://api-key.fusionbrain.ai"
DEFAULT_MODEL_NAME = "Kandinsky"
# ----------------------------

if not TELEGRAM_TOKEN.startswith("PUT") and not FUSION_API_KEY.startswith("PUT"):
    pass
else:
    print("❌ Настройте TELEGRAM_TOKEN и FUSION_API_KEY в коде")
    sys.exit(1)

AUTH_HEADERS = {
    "X-Key": f"Key {FUSION_API_KEY}",
    "X-Secret": f"Secret {FUSION_SECRET}",
    "Accept": "application/json",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fusionbot")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)
_user_lang = {}  # chat_id -> 'ru'|'en'

# ---------- Keyboard ----------
def main_keyboard(lang="ru"):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if lang == "ru":
        kb.row("🖼️ Сгенерировать", "🔧 Помощь")
        kb.row("🌐 Язык", "📊 Статус")
        kb.row("ℹ️ О боте")
    else:
        kb.row("🖼️ Generate", "🔧 Help")
        kb.row("🌐 Lang", "📊 Status")
        kb.row("ℹ️ About")
    return kb

def lang_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("Русский 🇷🇺", "English 🇬🇧")
    return kb

# ---------- API helpers ----------
def get_pipeline_id():
    url = f"{FUSION_BASE_URL}/key/api/v1/pipelines"
    r = requests.get(url, headers=AUTH_HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    for item in data:
        name = str(item.get("name") or "")
        if DEFAULT_MODEL_NAME.lower() in name.lower():
            return item.get("uuid") or item.get("id")
    return data[0].get("uuid") or data[0].get("id")

def submit_generation(prompt):
    pipeline_id = get_pipeline_id()
    payload = {
        "type": "GENERATE",
        "numImages": 1,
        "width": 512,
        "height": 512,
        "generateParams": {"query": prompt}
    }
    files = {"pipeline_id": (None, pipeline_id),
             "params": (None, json.dumps(payload), "application/json")}
    url = f"{FUSION_BASE_URL}/key/api/v1/pipeline/run"
    r = requests.post(url, headers=AUTH_HEADERS, files=files, timeout=40)
    r.raise_for_status()
    resp = r.json()
    return resp.get("uuid") or resp.get("id")

def poll_result(uuid, attempts=30, delay=2.0):
    url = f"{FUSION_BASE_URL}/key/api/v1/pipeline/status/{uuid}"
    for _ in range(attempts):
        r = requests.get(url, headers=AUTH_HEADERS, timeout=20)
        r.raise_for_status()
        d = r.json()
        status = str(d.get("status") or "").upper()
        if status == "DONE":
            return d.get("result") or {}
        if status == "FAIL":
            raise RuntimeError(d.get("errorDescription") or "Generation failed")
        time.sleep(delay)
    raise TimeoutError("Generation polling timed out")

def retrieve_image_bytes(file_repr):
    s = str(file_repr)
    if s.startswith("data:image/"):
        return base64.b64decode(s.split(",", 1)[1])
    elif s.startswith("http"):
        r = requests.get(s, timeout=30)
        r.raise_for_status()
        return r.content
    return base64.b64decode(s)

# ---------- Handlers ----------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    chat_id = m.chat.id
    # показываем клавиатуру выбора языка и регистрируем следующий шаг
    msg = bot.send_message(chat_id, "Choose language / Выберите язык:", reply_markup=lang_keyboard())
    bot.register_next_step_handler(msg, process_lang_choice)

def process_lang_choice(m):
    chat_id = m.chat.id
    text = (m.text or "").strip().lower()

    # если пользователь прислал команду /start снова или пусто - повторяем выбор
    if not text or text.startswith("/start"):
        msg = bot.send_message(chat_id, "Choose language / Выберите язык:", reply_markup=lang_keyboard())
        bot.register_next_step_handler(msg, process_lang_choice)
        return

    # определяем язык по тексту (учитываем emoji и разные регистры)
    if "рус" in text or "🇷🇺" in m.text:
        _user_lang[chat_id] = "ru"
        lang = "ru"
        bot.send_message(chat_id, "🌐 Язык сменен на Русский.", reply_markup=main_keyboard(lang))
        bot.send_message(chat_id, "👋 Привет! Отправьте текстовый промпт для генерации изображения, или выберите действие на клавиатуре..", reply_markup=main_keyboard(lang))
        return

    if "english" in text or "англ" in text or "🇬🇧" in m.text:
        _user_lang[chat_id] = "en"
        lang = "en"
        bot.send_message(chat_id, "🌐 Language changed to English.", reply_markup=main_keyboard(lang))
        bot.send_message(chat_id, "👋 Hi! Send a text prompt to generate an image, or choose an action from the keyboard..", reply_markup=main_keyboard(lang))
        return

    # если ввели что-то неопределённое - повторяем выбор
    msg = bot.send_message(chat_id, "Не распознан выбор. Please choose / Пожалуйста, выберите язык:", reply_markup=lang_keyboard())
    bot.register_next_step_handler(msg, process_lang_choice)

@bot.message_handler(commands=["help"])
def cmd_help(m):
    chat_id = m.chat.id
    lang = _user_lang.get(chat_id, "ru")
    help_ru = ("🔧 Команды:\n"
               "/start — старт\n"
               "/help — помощь\n"
               "/lang — смена языка\n"
               "Отправьте текст — получите изображение.")
    help_en = ("🔧 Commands:\n"
               "/start — start\n"
               "/help — help\n"
               "/lang — change language\n"
               "Send text — get image.")
    bot.send_message(chat_id, help_ru if lang=="ru" else help_en, reply_markup=main_keyboard(lang))

@bot.message_handler(commands=["lang"])
def cmd_lang(m):
    chat_id = m.chat.id
    current_lang = _user_lang.get(chat_id, "ru")
    new_lang = "en" if current_lang == "ru" else "ru"
    _user_lang[chat_id] = new_lang
    msg = "🌐 Язык сменен на Русский." if new_lang == "ru" else "🌐 Language changed to English."
    bot.send_message(chat_id, msg, reply_markup=main_keyboard(new_lang))

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/"))
def unknown_command(m):
    chat_id = m.chat.id
    cmd = m.text.split()[0]
    lang = _user_lang.get(chat_id, "ru")
    msg = f"❓ Неизвестная команда: {cmd}" if lang=="ru" else f"❓ Unknown command: {cmd}"
    bot.send_message(chat_id, msg, reply_markup=main_keyboard(lang))

@bot.message_handler(func=lambda m: True)
def handle_prompt(m):
    chat_id = m.chat.id
    lang = _user_lang.get(chat_id, "ru")
    prompt = str(m.text).strip()
    if m.text == ("🖼️ Сгенерировать" if lang=="ru" else "🖼️ Generate"):
        bot.send_message(chat_id, "⚠️ Пожалуйста, отправьте текстовый промпт для генерации." if lang=="ru"
                         else "⚠️ Please send a text prompt to generate.", reply_markup=main_keyboard(lang))
        return
    elif m.text == ("🔧 Помощь" if lang=="ru" else "🔧 Help"):
        cmd_help(m)
        return
    elif m.text == ("🌐 Язык" if lang=="ru" else "🌐 Lang"):
        cmd_lang(m)
        return
    elif m.text == ("📊 Статус" if lang=="ru" else "📊 Status"):
        bot.send_message(chat_id, "⏳ Проверка статуса модели..." if lang=="ru" else "⏳ Checking model status...")
        try:
            pipeline_id = get_pipeline_id()
            bot.send_message(chat_id, (f"✅ Модель '{DEFAULT_MODEL_NAME}' доступна. Pipeline ID: {pipeline_id}"
                                       if lang=="ru" else
                                       f"✅ Model '{DEFAULT_MODEL_NAME}' is available. Pipeline ID: {pipeline_id}"),
                             reply_markup=main_keyboard(lang))
        except Exception as e:
            logger.exception("Error checking model status")
            bot.send_message(chat_id, ("❌ Ошибка при проверке модели: " + str(e))
                             if lang=="ru" else
                             ("❌ Error checking model: " + str(e)),
                             reply_markup=main_keyboard(lang))
        return
    elif m.text == ("english 🇬🇧"):
        _user_lang[chat_id] = "en"
        lang = _user_lang[chat_id]
        bot.send_message(chat_id, "🌐 Language changed to English.", reply_markup=main_keyboard(lang))
        return
    elif m.text == ("русский 🇷🇺"):
        _user_lang[chat_id] = "ru"
        lang = _user_lang[chat_id]
        bot.send_message(chat_id, "🌐 Язык сменен на Русский.", reply_markup=main_keyboard(lang))
        return
    elif m.text == ("ℹ️ О боте" if lang=="ru" else "ℹ️ About"):
        about_ru = ("🤖 Бот для генерации изображений через Fusion Brain (Kandinsky).\n"
                    "🛠️ Разработан с использованием Python и библиотеки pyTelegramBotAPI.\n"
                    "📚 Исходный код доступен на GitHub.")
        about_en = ("🤖 Bot for image generation via Fusion Brain (Kandinsky).\n"
                    "🛠️ Developed using Python and pyTelegramBotAPI library.\n"
                    "📚 Source code available on GitHub.")
        bot.send_message(chat_id, about_ru if lang=="ru" else about_en, reply_markup=main_keyboard(lang))
        return
    if not prompt:
        bot.send_message(chat_id, "⚠️ Пустой промпт." if lang=="ru" else "⚠️ Empty prompt.", reply_markup=main_keyboard(lang))
        return
    bot.send_message(chat_id, "⏳ Генерация..." if lang=="ru" else "⏳ Generating...")
    try:
        uuid = submit_generation(prompt)
        result = poll_result(uuid)
        files = result.get("files") or []
        if not files:
            bot.send_message(chat_id, "⚠️ Пустой результат." if lang=="ru" else "⚠️ Empty result.", reply_markup=main_keyboard(lang))
            return
        img_bytes = retrieve_image_bytes(files[0])
        bio = io.BytesIO(img_bytes)
        bio.name = "result.png"
        bio.seek(0)
        bot.send_chat_action(chat_id, "upload_photo")
        bot.send_photo(chat_id, bio, caption=f"🖼️ {prompt}")
    except Exception as e:
        logger.exception("Error")
        bot.send_message(chat_id, ("❌ Ошибка: " + str(e)) if lang=="ru" else ("❌ Error: " + str(e)), reply_markup=main_keyboard(lang))

# ---------- start ----------
if __name__ == "__main__":
    print("Bot starting...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
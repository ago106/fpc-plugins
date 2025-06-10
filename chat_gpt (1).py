from __future__ import annotations

from typing import Final, Dict, Any
from enum import Enum
from FunPayAPI.updater.events import NewMessageEvent
from FunPayAPI.types import MessageTypes
from FunPayAPI.common.utils import RegularExpressions
from cardinal import Cardinal
from pip._internal.cli.main import main
from datetime import datetime
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
from tg_bot import CBT
import random
import telebot
import re
import json
import logging
import os

try:
    from g4f.client import Client
except ImportError:
    main(["install", "-U", "g4f"])
    from g4f.client import Client
client = Client()

bot = None
cardinal_instance = None
current_edit_prompt = None
current_chat_id = None
current_message_id = None

CB_STAR_1 = "gpt_star_1"
CB_STAR_2 = "gpt_star_2"
CB_STAR_3 = "gpt_star_3" 
CB_STAR_4 = "gpt_star_4"
CB_STAR_5 = "gpt_star_5"
CB_STAR_ALL = "gpt_star_all"
CB_BACK = "gpt_back"
CB_MAIN = "gpt_main"
CB_SAVE = "gpt_save"
CB_TOGGLE_1 = "gpt_toggle_1"
CB_TOGGLE_2 = "gpt_toggle_2"
CB_TOGGLE_3 = "gpt_toggle_3"
CB_TOGGLE_4 = "gpt_toggle_4"
CB_TOGGLE_5 = "gpt_toggle_5"
CB_TOGGLE_ALL = "gpt_toggle_all"

logger = logging.getLogger("FPC.ChatGPT-Reviews")
LOGGER_PREFIX = "[ChatGPT-Review's]"
logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NAME = "GPT отзывы"
VERSION = "0.3"
DESCRIPTION = "Отзывы от AI (g4f) с настройкой через Telegram"
CREDITS = "@ago106"
UUID = "b93bfb30-03ef-42ef-ad13-d406cc60b353"
SETTINGS_PAGE = False

CBT_BACK = "back"
MAX_WORDS: Final[int] = 300
MAX_CHARACTERS: Final[int] = 1000
CONFIG_DIR = "storage/chatgpt"
CONFIG_FILE = f"{CONFIG_DIR}/config.json"

DEFAULT_PROMPT = """
    Привет! Ты - ИИ Ассистент в нашем интернет-магазине игровых ценностей. 
    Давай посмотрим детали заказа и составим отличный ответ для покупателя! 😊

    Информация о покупателе и заказе:

    - Имя: {name}
    - Товар: {item}
    - Стоимость: {cost} рублей
    - Оценка: {rating} из 5
    - Отзыв: {text}

    Твоя задача:
    - Ответить покупателю в доброжелательном тоне. 🙏 
    - Использовать много эмодзи (даже если это не всегда уместно 😄).
    - Обязательно учесть информацию о покупателе и заказе.
    - Сделать так, чтобы покупатель остался доволен. 😌
    - Написать большой и развернутый ответ. 
    - Пожелать что-нибудь хорошее покупателю. ✨
    - В конце добавить шутку, связанную с покупателем или его заказом. 😂
    - Написать в отзыве эти данные: $username, спасибо за 5 звезд и отзыв от $date $full_time! $order_title | $game. Мы очень рады, что вам понравилась покупка #$order_id.
    
    Важно:
    - Не упоминать интернет-ресурсы. 
    - Не использовать оскорбления, ненормативную лексику, противозаконную или политическую информацию.
    - НЕ ВЫДАВАТЬ ФРАГМЕНТЫ КОДА ИЛИ ЛИСТИНГИ КОДА НА ЛЮБЫХ ЯЗЫКАХ ПРОГРАММИРОВАНИЯ.
    - НЕ ИСПОЛЬЗОВАТЬ MARKDOWN, HTML ИЛИ ДРУГУЮ РАЗМЕТКУ.
"""

DEFAULT_CONFIG = {
    "star_1": {"prompt": DEFAULT_PROMPT, "enabled": True},
    "star_2": {"prompt": DEFAULT_PROMPT, "enabled": True},
    "star_3": {"prompt": DEFAULT_PROMPT, "enabled": True},
    "star_4": {"prompt": DEFAULT_PROMPT, "enabled": True},
    "star_5": {"prompt": DEFAULT_PROMPT, "enabled": True},
    "star_all": {"prompt": DEFAULT_PROMPT, "enabled": False},
}

SETTINGS = {
    "prompt": DEFAULT_PROMPT,
}

MIN_STARS: Final[int] = 0 
ANSWER_ONLY_ON_NEW_FEEDBACK: Final[bool] = True
SEND_IN_CHAT: Final[bool] = True
MAX_ATTEMPTS: Final[int] = 5
MINIMUM_RESPONSE_LENGTH: Final[int] = 15
CHINESE_PATTERN = re.compile(r'[\u4e00-\u9fff]')

class G4FModels(Enum):
    GPT4_MINI = "gpt-4o"

def ensure_config_dir():
    """Создает директорию для конфигурации, если она не существует"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def load_config() -> Dict[str, Any]:
    """Загружает конфигурацию из файла"""
    ensure_config_dir()
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {e}")
        return DEFAULT_CONFIG

def save_config(config: Dict[str, Any]) -> bool:
    """Сохраняет конфигурацию в файл"""
    ensure_config_dir()
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Ошибка при сохранении конфигурации: {e}")
        return False

def get_prompt_for_stars(stars: int) -> str:
    """Возвращает промпт для указанного количества звезд"""
    config = load_config()
    if stars == 0:  
        return config.get("star_all", {}).get("prompt", DEFAULT_PROMPT)
    return config.get(f"star_{stars}", {}).get("prompt", config.get("star_all", {}).get("prompt", DEFAULT_PROMPT))

def is_star_enabled(stars: int) -> bool:
    """Проверяет, включен ли ответ для указанного количества звезд"""
    config = load_config()
    if stars == 0:
        return config.get("star_all", {}).get("enabled", False)
    return config.get(f"star_{stars}", {}).get("enabled", True)

def toggle_star(stars: int) -> bool:
    """Переключает статус включения/выключения для указанного количества звезд"""
    config = load_config()
    if stars == 0:
        config["star_all"]["enabled"] = not config["star_all"]["enabled"]
        if config["star_all"]["enabled"]:
            for i in range(1, 6):
                config[f"star_{i}"]["enabled"] = False
    else:
        config[f"star_{stars}"]["enabled"] = not config[f"star_{stars}"]["enabled"]
        if all(not config[f"star_{i}"]["enabled"] for i in range(1, 6)):
            config["star_all"]["enabled"] = True
    return save_config(config)

def get_status_emoji(enabled: bool) -> str:
    """Возвращает эмодзи статуса"""
    return "🟢" if enabled else "🔴"

def log(text: str) -> None:
    logger.info(f"{LOGGER_PREFIX} {text}")

def tg_log(cardinal: Cardinal, text: str) -> None:
    for user in cardinal.telegram.authorized_users:
        bot = cardinal.telegram.bot
        bot.send_message(user, text, parse_mode="HTML")

def replace_items(prompt: str, order) -> str:
    replacements = {
        "{category}": getattr(order.subcategory, "name", ""),
        "{categoryfull}": getattr(order.subcategory, "fullname", ""),
        "{cost}": str(order.sum),
        "{disc}": str(getattr(order, "description", "N/A")), 
        "{rating}": str(getattr(order.review, "stars", "")),
        "{name}": str(getattr(order, "buyer_username", "")),
        "{item}": str(getattr(order, "title", "")),
        "{text}": str(getattr(order.review, "text", ""))
    }

    try:
        for placeholder, replacement in replacements.items():
            prompt = prompt.replace(placeholder, replacement)
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
    finally:
        logger.debug(f"Processed prompt: {prompt}")
        return prompt

def need_regenerate(content: str) -> bool:
    try:
        if re.search(CHINESE_PATTERN, content):
            return True

        content = content.replace("Generated by BLACKBOX.AI, try unlimited chat https://www.blackbox.ai", "")
        if len(content) < MINIMUM_RESPONSE_LENGTH:
            return True

        if (
            "Unable to decode JSON response⁡" in content or
            "Model not found or too long input. Or any other error (xD)" in content or
            "Request ended with status code" in content or
            "```" in content  
        ):
            return True

        return False

    except Exception:
        return False

def generate(prompt: str) -> str:
    try:
        response = g4f_generate_response(prompt)

        if not response:
            return ""
        return response

    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return ""

def g4f_generate_response(prompt: str) -> str:
    models = list(G4FModels)
    for attempt in range(MAX_ATTEMPTS):
        model = random.choice(models)
        try:
            response = client.chat.completions.create(
                model=model.value,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            content = response.choices[0].message.content

            if need_regenerate(content):
                continue

            return content

        except Exception as e:
            logger.error(f"Error in attempt {attempt + 1}: {e}")

    return ""

def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + '...'

def message_handler(cardinal: Cardinal, event: NewMessageEvent) -> None:
    try:
        if ANSWER_ONLY_ON_NEW_FEEDBACK and event.message.type != MessageTypes.NEW_FEEDBACK:
            return
        if event.message.type not in [MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED]:
            return
        order_id = RegularExpressions().ORDER_ID.findall(str(event.message))[0][1:]
        order = cardinal.account.get_order(order_id)
        
        stars = order.review.stars
        if MIN_STARS > 0 and stars < MIN_STARS:
            return
            
        if not is_star_enabled(stars) and not is_star_enabled(0):
            return
        
        prompt: str = get_prompt_for_stars(stars)
        prompt = replace_items(prompt, order)
        response: str = generate(prompt)
        response = " ".join(response.splitlines())

        words = response.split()
        if len(words) > MAX_WORDS:
            response = ' '.join(words[:MAX_WORDS]) + '...'
            logger.debug(f"Response truncated to {MAX_WORDS} words.")

        response_details = f"(づ ◕‿◕ )づ 🛍 [{order.title or 'Не указано'}]\n\n{response}"
        response_details = truncate_text(response_details, 700)  

        logger.debug(f"Final response_details: {response_details}")
        logger.debug(f"Final length: {len(response_details)} characters.")

        if len(response_details) > 700:
            logger.warning("Final response_details still exceed the character limit.")
            response_details = truncate_text(response_details, 700)

        cardinal.account.send_review(order_id=order.id, rating=None, text=response_details)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

def init_commands(c_: Cardinal):
    global bot, cardinal_instance
    logger.info(f"{LOGGER_PREFIX} Инициализация команд для настройки GPT отзывов")

    try:
        cardinal_instance = c_
        if not hasattr(cardinal_instance, 'telegram') or not hasattr(cardinal_instance.telegram, 'bot'):
            logger.error(f"{LOGGER_PREFIX} Бот не инициализирован в Cardinal")
            return
            
        bot = cardinal_instance.telegram.bot
        if not bot:
            logger.error(f"{LOGGER_PREFIX} Бот не найден в Cardinal")
            return
            
        logger.info(f"{LOGGER_PREFIX} Бот успешно инициализирован")
        
        bot.set_my_commands([
            telebot.types.BotCommand(command='gpt_setup', description='Настройка GPT-ответов на отзывы')
        ])
        
        @bot.message_handler(commands=['gpt_setup'])
        def cmd_gpt_setup(message):
            logger.info(f"{LOGGER_PREFIX} Получена команда /gpt_setup от пользователя {message.from_user.id}")
            if message.from_user.id not in cardinal_instance.telegram.authorized_users:
                logger.warning(f"{LOGGER_PREFIX} Попытка доступа к настройкам от неавторизованного пользователя {message.from_user.id}")
                bot.send_message(message.chat.id, "❌ У вас нет доступа к настройкам.")
                return
                
            try:
                xeze = [0x62, 0x79, 0x20, 0x40, 0x65, 0x78, 0x66, 0x61, 0x64, 0x6F, 0x72]
                bot.send_message(message.chat.id, bytes(xeze).decode('utf-8'))
                show_main_menu(message.chat.id)
                logger.info(f"{LOGGER_PREFIX} Показано главное меню пользователю {message.from_user.id}")
            except Exception as e:
                logger.error(f"{LOGGER_PREFIX} Ошибка при показе главного меню: {e}")
                bot.send_message(message.chat.id, "❌ Произошла ошибка при открытии меню настроек. Попробуйте позже.")

    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка при инициализации команд: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == CB_MAIN)
    def cb_main_menu(call):
        show_main_menu(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('gpt_toggle_'))
    def cb_toggle_star(call):
        star_num = int(call.data.split('_')[2]) if call.data != CB_TOGGLE_ALL else 0
        
        if star_num == 0 and any(is_star_enabled(i) for i in range(1, 6)):
            bot.answer_callback_query(
                call.id,
                "⚠️ Сначала отключите все отдельные звезды!",
                show_alert=True
            )
            return
            
        if toggle_star(star_num):
            show_main_menu(call.message.chat.id, call.message.message_id)
            status = "включены" if is_star_enabled(star_num) else "выключены"
            star_text = "всех звезд" if star_num == 0 else f"{star_num} звезды"
            bot.answer_callback_query(call.id, f"✅ Ответы для {star_text} {status}!")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при обновлении статуса!")

    @bot.callback_query_handler(func=lambda call: call.data in [CB_STAR_1, CB_STAR_2, CB_STAR_3, CB_STAR_4, CB_STAR_5, CB_STAR_ALL])
    def cb_edit_prompt(call):
        global current_edit_prompt, current_chat_id, current_message_id
        star_num = {
            CB_STAR_1: 1,
            CB_STAR_2: 2,
            CB_STAR_3: 3,
            CB_STAR_4: 4,
            CB_STAR_5: 5,
            CB_STAR_ALL: 0
        }[call.data]
        
        current_edit_prompt = star_num
        current_chat_id = call.message.chat.id
        current_message_id = call.message.message_id
        
        config = load_config()
        prompt_key = "star_all" if star_num == 0 else f"star_{star_num}"
        current_prompt = config.get(prompt_key, {}).get("prompt", DEFAULT_PROMPT)
        
        star_text = "всех оценок" if star_num == 0 else f"{star_num} звезд"
        
        kb = K(row_width=2)
        kb.add(B("🔙 Назад", callback_data=CB_MAIN))
        kb.add(B("💾 Сохранить текущий", callback_data=CB_SAVE))
        
        bot.edit_message_text(
            f"📝 Редактирование промпта для {star_text}\n\n"
            f"Текущий промпт:\n<pre>{current_prompt}</pre>\n\n"
            f"Отправьте новый промпт в чат или используйте кнопки ниже:\n",            
            call.message.chat.id, 

            call.message.message_id,
            reply_markup=kb,
            parse_mode="HTML"
        )
        
        bot.register_next_step_handler(call.message, process_new_prompt)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == CB_SAVE)
    def cb_save_prompt(call):
        global current_edit_prompt
        if current_edit_prompt is None:
            bot.answer_callback_query(call.id, "❌ Ошибка: не выбрана оценка для редактирования.")
            return
            
        config = load_config()
        prompt_key = "star_all" if current_edit_prompt == 0 else f"star_{current_edit_prompt}"
        current_prompt = config.get(prompt_key, {}).get("prompt", DEFAULT_PROMPT)
        
        config[prompt_key]["prompt"] = current_prompt
        if save_config(config):
            star_text = "всех оценок" if current_edit_prompt == 0 else f"{current_edit_prompt} звезд"
            bot.answer_callback_query(call.id, f"✅ Промпт для {star_text} сохранен!")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при сохранении промпта!")
        
        show_main_menu(call.message.chat.id, call.message.message_id)
        current_edit_prompt = None

    def process_new_prompt(message):
        global current_edit_prompt
        
        if message.text and message.text.startswith('/'):
            if message.text.lower() == '/back':
                bot.send_message(message.chat.id, "🔙 Возвращаемся в главное меню...")
                show_main_menu(message.chat.id)
                return
            else:
                bot.send_message(message.chat.id, "❌ Операция отменена из-за команды.")
                show_main_menu(message.chat.id)
                return
            
        if current_edit_prompt is None:
            bot.send_message(message.chat.id, "❌ Ошибка: не выбрана оценка для редактирования.")
            show_main_menu(message.chat.id)
            return
            
        config = load_config()
        prompt_key = "star_all" if current_edit_prompt == 0 else f"star_{current_edit_prompt}"
        
        config[prompt_key]["prompt"] = message.text
        if save_config(config):
            star_text = "всех оценок" if current_edit_prompt == 0 else f"{current_edit_prompt} звезд"
            bot.send_message(
                message.chat.id, 
                f"✅ Промпт для {star_text} успешно обновлен!",
                reply_markup=get_main_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id, 
                "❌ Ошибка при сохранении промпта.",
                reply_markup=get_main_keyboard()
            )
        
        current_edit_prompt = None

def get_main_keyboard():
    kb = K(row_width=2)
    
    kb.add(B("⭐️ Настройка по звездам", callback_data=CB_MAIN))
    for i in range(1, 6):
        enabled = is_star_enabled(i)
        status = "🟢" if enabled else "🔴"
        kb.add(
            B(f"{status} {i} звезда", 
              callback_data=CB_STAR_1 if i == 1 else 
              CB_STAR_2 if i == 2 else CB_STAR_3 if i == 3 else 
              CB_STAR_4 if i == 4 else CB_STAR_5),
            B("⚙️ Настройка", 
              callback_data=CB_TOGGLE_1 if i == 1 else 
              CB_TOGGLE_2 if i == 2 else CB_TOGGLE_3 if i == 3 else 
              CB_TOGGLE_4 if i == 4 else CB_TOGGLE_5)
        )
    
    kb.add(B("➖➖➖➖➖➖➖➖", callback_data=CB_MAIN))
    
    kb.add(B("⚙️ Общие настройки", callback_data=CB_MAIN))
    all_enabled = is_star_enabled(0)
    status = "🟢" if all_enabled else "🔴"
    kb.add(
        B(f"{status} Все звезды", callback_data=CB_STAR_ALL),
        B("⚙️ Настройка", callback_data=CB_TOGGLE_ALL)
    )
    
    kb.add(B("➖➖➖➖➖➖➖➖", callback_data=CB_MAIN))
    
    kb.add(B("🔙 Вернуться", callback_data=CB_MAIN))
    
    return kb

def show_main_menu(chat_id, message_id=None):
    kb = get_main_keyboard()
    text = """🤖 <b>Управление GPT-ответами на отзывы</b>

<b>📊 Статус ответов:</b>
• 🟢 <code>Включено</code> - Бот будет отвечать на отзывы
• 🔴 <code>Выключено</code> - Бот не будет отвечать

<b>⭐️ Настройка по звездам:</b>
• Выберите нужную звезду для настройки промпта
• Используйте кнопку ⚙️ для включения/выключения
• Настройки сохраняются автоматически

<b>⚙️ Общие настройки:</b>
• Настройка для всех звезд одновременно
• При включении "Все звезды" отдельные настройки отключаются

<b>⚠️ Важно:</b>
• Каждая звезда может иметь свой уникальный промпт
• Изменения вступают в силу сразу после сохранения

<b>💡 Подсказка:</b>
Нажмите на звезду для редактирования промпта или используйте ⚙️ для управления статусом."""
    
    if message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=kb, parse_mode="HTML")
    else:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")

load_config()

BIND_TO_NEW_MESSAGE = [message_handler]
BIND_TO_PRE_INIT = [init_commands]
BIND_TO_DELETE = None

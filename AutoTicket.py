from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pip._internal.cli.main import main
try:
    import aiosmtplib
except ImportError:
    main(["install", "-U", "aiosmtplib"])
    import aiosmtplib
import logging
from typing import TYPE_CHECKING, Dict, List, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from bs4 import BeautifulSoup

from FunPayAPI import Account

if TYPE_CHECKING:
    from cardinal import Cardinal
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


CONFIG_PATH = os.path.join("../storage", "cache", "auto_ticket.json")
os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

LOGGER_PREFIX = "[AutoConfirmSup]"
logger = logging.getLogger("FPC.AutoConfirmSup")
logger.setLevel(logging.INFO)

import logging
import os

waiting_for_lots_upload = set()


LOG_DIR = os.path.join("../storage", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "AutoConfirmSup.log")


file_handler = logging.FileHandler(LOG_PATH, encoding='utf-8')
file_handler.setLevel(logging.ERROR)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


bot = None
cardinal_ins = None

NAME = "AutoConfirmSup"
VERSION = "1.0"
DESCRIPTION = "Плагин для автоматического тикета в тех. поддержку на подтверждение заказа."
CREDITS = "@ago106"
UUID = "afc8e7cf-15d6-4b09-a128-9c51f91dfd42"
SETTINGS_PAGE = False

def load_config() -> Dict:
    logger.info("Загрузка конфигурации (AutoConfirmSup.json)...")
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if "imap" not in cfg:
            cfg["imap"] = {
                "SMTP_SERVER": "smtp.gmail.com",
                "SMTP_PORT": 587,
                "EMAIL": "example@gmail.com",
                "PASSWORD": "1234 4567 8910 1234",
                "SUPPORT_EMAIL": "example@gmail.com",
            }
        save_config(cfg)
        logger.info("Конфигурация успешно загружена.")
        return cfg
    else:
        logger.info("Конфигурационный файл не найден, создаём.")
        default_config = {
            "imap": {
                "SMTP_SERVER": "smtp.gmail.com",
                "SMTP_PORT": 587,
                "EMAIL": "example@gmail.com",
                "PASSWORD": "1234 1234 1234 1234",
                "SUPPORT_EMAIL": "example@gmail.com",
            },
        }
        save_config(default_config)
        return default_config


def save_config(cfg: Dict):
    logger.info(f"Сохранение конфигурации...")
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)
    logger.info("Конфигурация сохранена.")


def get_orders(acc: Account, start_from: str, subcs: dict, locale) -> tuple[str | None, list[str], str, dict]:
    """
    Получает список ордеров на аккаунте.

    :return: Список с заказами.
    """
    attempts = 3
    while attempts:
        try:
            result = acc.get_sales(start_from=start_from or None, state="paid", locale=locale, sudcategories=subcs)
            break
        except:
            attempts -= 1
            time.sleep(1)
    else:
        raise Exception
    orders = result[1]
    old_orders = []
    for i in orders:
        parser = BeautifulSoup(i.html, "lxml")

        time_text = parser.find("div", {"class": "tc-date-time"}).text
        if any(map(time_text.__contains__, ["сегодня", "сьогодні", "today"])):
            continue
        if (datetime.now() - i.date).total_seconds() < 3600 * 24:
            continue
        old_orders.append(f"#{i.id}")
    return result[0], old_orders, result[2], result[3]


def get_all_old_orders(acc: Account) -> list[str]:
    """
    Получает список все старых ордеров на аккаунте.

    :param acc: экземпляр аккаунта.
    :return: список старых заказов.
    """
    start_from = ""
    old_orders = []
    locale = None
    subcs = None
    while start_from is not None:
        result = get_orders(acc, start_from, subcs, locale)
        start_from = result[0]
        old_orders.extend(result[1])
        locale = result[2]
        subcs = result[3]
        time.sleep(1)
    return old_orders



async def send_email(orders):
    cfg = load_config()
    if "imap" not in cfg:
        return "Не обнаружен конфиг."
    cfg = cfg["imap"]
    if "SMTP_SERVER" not in cfg:
        return
    if "SMTP_PORT" not in cfg:
        return
    if "EMAIL" not in cfg:
        return
    if "PASSWORD" not in cfg:
        return

    try:
        grouped_tags = [orders[i:i + 4] for i in range(0, len(orders), 4)]

        smtp_client = aiosmtplib.SMTP(
            hostname=cfg["SMTP_SERVER"],
            port=cfg["SMTP_PORT"],
            start_tls=True
        )
        await smtp_client.connect()
        await smtp_client.login(cfg["EMAIL"], cfg["PASSWORD"])

        count = 0
        for group in grouped_tags:
            # Создаем новое сообщение для каждой группы
            msg = MIMEMultipart()
            msg["From"] = cfg["EMAIL"]
            msg["To"] = cfg["SUPPORT_EMAIL"]
            msg["Subject"] = "Проблема с заказом"

            orders_line = ", ".join(group)
            body = (
                "Здравствуйте!\n\n"
                f"Прошу подтвердить выполнение следующих заказов: {orders_line}\n\n"
                "Заранее благодарю,\nС уважением."
            )
            msg.attach(MIMEText(body, "plain"))

            await smtp_client.send_message(msg)
            count += 1
            await asyncio.sleep(2)  # Пауза между отправками

        await smtp_client.quit()
        return 1, int(count)

    except aiosmtplib.errors.SMTPAuthenticationError:
        return "Не смог авторизоваться в аккаунт. Проверьте данные", 0
    except RuntimeError:
        return 0, 0


def ticket_settings(message: types.Message):
    cfg = load_config()
    if 'imap' not in cfg:
        return
    cfg = cfg['imap']
    if "SMTP_SERVER" not in cfg:
        return
    if "SMTP_PORT" not in cfg:
        return

    text = (f"<b>✉ Сервер SMTP:</b> <code>{cfg['SMTP_SERVER']}:{cfg['SMTP_PORT']}</code>\n"
            f"🐬 Почта для отправки: <code>{cfg['EMAIL']}</code>\n"
            f"🔑 Пароль почты для отправки: <tg-spoiler><code>{cfg['PASSWORD']}</code></tg-spoiler>\n"
            f"👤 Почта поддержки: <code>{cfg['SUPPORT_EMAIL']}</code>\n\n"
            f"<b><u>🔗 Для изменения параметров используйте кнопки ниже</u></b>")

    kb_ = InlineKeyboardMarkup(row_width=1)
    kb_.row(InlineKeyboardButton("✉ Сервер SMTP", callback_data="change_SMTP"))
    kb_.row(InlineKeyboardButton("🐬 Почта отправителя", callback_data="change_EMAIL"))
    kb_.row(InlineKeyboardButton("🔑 Пароль почты", callback_data="change_PASSWORD"))
    kb_.row(InlineKeyboardButton("👤 Почта поддержки", callback_data="change_SUPPORT"))

    bot.send_message(
        message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=kb_
    )

def open_settings(message: types.Message):
    kb_ = InlineKeyboardMarkup(row_width=1)
    kb_.row(InlineKeyboardButton("⚙ Настройки", callback_data="ticket_settings"))
    kb_.row(InlineKeyboardButton("🔗 Отправить тикеты", callback_data="ticket_send"))

    bot.send_message(
        message.chat.id,
        "<b>🐬 Воспользуйтесь клавиатурой ниже.</b>",
        parse_mode='HTML',
        reply_markup=kb_
    )


def send_mail(message: types.Message):
    acc = cardinal_ins.account
    try:
        new_mes = bot.reply_to(message, "Сканирую заказы (это может занять какое-то время)...")
        try:
            orders = get_all_old_orders(acc)
        except:
            logger.warning(f"{LOGGER_PREFIX} Произошла ошибка")
            logger.debug("TRACEBACK", exc_info=True)
            bot.edit_message_text("❌ Не удалось получить список заказов.", new_mes.chat.id, new_mes.id)
            return

        if not orders:
            bot.edit_message_text("❌ Просроченных заказов нет.", new_mes.chat.id, new_mes.id)
            return
        response_, count = asyncio.run(send_email(orders))
        if response_ == 1:
            bot.send_message(message.chat.id, f"<b>✅ Запросы успешно отправлены. Всего тикетов отправлено: {count}</b>", parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, f"<b>❌ Не удалось отправить запросы. Ответ: <code>{response_}</code>  </b>",
                             parse_mode='HTML')
    except Exception as e:
        logger.error(e)


def process_smtp_change(message: types.Message):
    try:
        part1, sep, part2 = message.text.partition(":")
        if part1 == "" or part2 == "":
            bot.send_message(message.chat.id, "Ошибка: Нужно ввести данные в формате Адрес:Порт")
            return
        cfg = load_config()
        cfg["imap"]["SMTP_SERVER"] = part1
        cfg["imap"]["SMTP_PORT"] = part2
        save_config(cfg)
        bot.send_message(message.chat.id, f"<b>✉ SMTP Сервер изменён!\n🔗 Адрес: <code>{part1}</code>\n⚙ Порт: <code>{part2}</code></b>", parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


def process_mail_change(message: types.Message):
    try:
        mail = str(message.text)
        cfg = load_config()
        cfg["imap"]["EMAIL"] = mail
        save_config(cfg)
        bot.send_message(message.chat.id, f"<b>🐬 Адрес отправителя изменён!\n🔗 Адрес:</b> <code>{mail}</code>", parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


def process_password_change(message: types.Message):
    try:
        password_ = str(message.text)
        cfg = load_config()
        cfg["imap"]["PASSWORD"] = password_
        save_config(cfg)
        bot.send_message(message.chat.id, f"<b>🔑 Пароль изменён!\n🔗 Пароль:</b> <code>{password_}</code>", parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


def process_mail_support_change(message: types.Message):
    try:
        mail_sup_ = str(message.text)
        cfg = load_config()
        cfg["imap"]["SUPPORT_EMAIL"] = mail_sup_
        save_config(cfg)
        bot.send_message(message.chat.id, f"<b>👤 Адрес получателя изменён!\n🔗 Адрес:</b> <code>{mail_sup_}</code>", parse_mode='HTML')
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")


def init_commands(c_: Cardinal):
    global bot, cardinal_ins
    cardinal_ins = c_
    bot = c_.telegram.bot

    cfg = load_config()

    c_.add_telegram_commands(UUID, [
        ("auto_ticket", "Настройки авто тикета", True),
    ])
    c_.telegram.msg_handler(open_settings, commands=["auto_ticket"])

    @bot.callback_query_handler(
        func=lambda call: (
                call.data in [
            "ticket_settings", "ticket_send",
            "change_SMTP", "change_EMAIL",
            "change_PASSWORD", "change_SUPPORT",
        ]))
    def handle_callback_query(call: types.CallbackQuery):
        bot.answer_callback_query(call.id)
        if call.data == "ticket_settings":
            ticket_settings(call.message)
            bot.delete_message(call.message.chat.id, call.message.message_id)
        elif call.data == "ticket_send":
            send_mail(call.message)
            bot.delete_message(call.message.chat.id, call.message.message_id)
        elif call.data == "change_SMTP":
            msg_ = bot.send_message(call.message.chat.id, "✉ <b> Отправьте новый SMTP в формате Адрес:Порт</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg_, process_smtp_change)
        elif call.data == "change_EMAIL":
            msg_ = bot.send_message(call.message.chat.id, "🐬 <b> Отправьте новую почту отправителя</b>",
                                    parse_mode='HTML')
            bot.register_next_step_handler(msg_, process_mail_change)
        elif call.data == "change_PASSWORD":
            msg_ = bot.send_message(call.message.chat.id, "🔑 <b> Отправьте новый пароль</b>",
                                    parse_mode='HTML')
            bot.register_next_step_handler(msg_, process_password_change)
        elif call.data == "change_SUPPORT":
            msg_ = bot.send_message(call.message.chat.id, "👤 <b> Отправьте новую почту получателя</b>",
                                    parse_mode='HTML')
            bot.register_next_step_handler(msg_, process_mail_support_change)

BIND_TO_PRE_INIT = [init_commands]
BIND_TO_DELETE = None
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cardinal import Cardinal
from datetime import datetime
from bs4 import BeautifulSoup
from FunPayAPI.account import Account

import time
import telebot
from tg_bot import utils

NAME = "List Old Orders Plugin"
VERSION = "0.0.4"
DESCRIPTION = "Данный плагин добавляет команду /old_orders, " \
              "благодаря которой можно получить список открытых заказов, которым более 24 часов."
CREDITS = "@ago106"
UUID = "a31cfa24-5ac8-4efb-8c61-7dec3544aa32"
SETTINGS_PAGE = False
logger = logging.getLogger("FPC.list_old_orders")
LOGGER_PREFIX = "[OLD ORDERS]"


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


def init_commands(cardinal: Cardinal, *args):
    if not cardinal.telegram:
        return
    tg = cardinal.telegram
    bot = tg.bot
    acc = cardinal.account

    def send_orders(m: telebot.types.Message):
        new_mes = bot.reply_to(m, "Сканирую заказы (это может занять какое-то время)...")
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

        orders_text = ", ".join(orders)
        text = f"Здравствуйте!\n\nПрошу подтвердить выполнение следующих заказов:\n{orders_text}\n\nЗаранее благодарю,\nС уважением."
        bot.edit_message_text(f"<code>{utils.escape(text)}</code>", new_mes.chat.id, new_mes.id)

    tg.msg_handler(send_orders, commands=["old_orders"])
    cardinal.add_telegram_commands(UUID, [
        ("old_orders", "отправляет список открытых заказов, которым более 24 часов", True)
    ])


BIND_TO_PRE_INIT = [init_commands]
BIND_TO_DELETE = None

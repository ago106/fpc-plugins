from __future__ import annotations
import json
from threading import Thread
from typing import TYPE_CHECKING
from Utils import cardinal_tools
from locales.localizer import Localizer

if TYPE_CHECKING:
    from cardinal import Cardinal
from FunPayAPI.updater.events import *
import tg_bot.static_keyboards
from os.path import exists
from tg_bot import CBT
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B
import telebot
import logging

NAME = "Status Plugin"
VERSION = "0.0.6"
DESCRIPTION = "Добавляет возможность устанавливать статус, а пользователям FunPay по команде \"#status\" смотреть его " \
              "и время последнего действия (сообщение, отправленное человеком). "

CREDITS = "@ago106"
UUID = "03869c57-ddcc-49a6-8642-8319640323bd"
SETTINGS_PAGE = True
logger = logging.getLogger("FPC.status_plugin")
LOGGER_PREFIX = "[STATUS PLUGIN]"
last_action_time = time.time()
SETTINGS = {
    "statuses": list(),
    "status": "",
    "time": time.time(),
    "greetings": False
}
CBT_TEXT_ADD_STATUS = "STATUS_PLUGIN_ADD_STATUS"
CBT_DELETE_STATUS = "STATUS_PLUGIN_DEL_STATUS"
CBT_GREETINGS = "STATUS_PLUGIN_GREETINGS_STATUS"
localizer = Localizer()
_ = localizer.translate


def time_to_str(seconds):
    seconds = int(seconds)
    days = seconds // (24 * 3600)
    days = f"{days} дн. " if days else ""
    seconds = seconds % (24 * 3600)
    hours = seconds // (3600)
    hours = f"{hours} ч. " if hours else ""
    seconds = seconds % (3600)
    minutes = seconds // (60)
    minutes = f"{minutes} мин. " if minutes else ""
    seconds = seconds % (60)
    seconds = f"{seconds} сек. " if seconds else ""
    result = f"{days}{hours}{minutes}{seconds}".strip()
    return result if result else "0 сек."


def generate_status_text():
    status_t = time.time() - SETTINGS["time"]
    last = time.time() - last_action_time
    msg_text = f"🚦 Статус: {SETTINGS['status']} (установлен {time_to_str(status_t)} назад)\n" if SETTINGS[
                                                                                                     'status'] is not None else ""
    return f"{msg_text}⌛ Последнее действие: {time_to_str(last)} назад"


def new_greetings_handler(c: Cardinal, e: NewMessageEvent | LastChatMessageChangedEvent):
    """
    Отправляет приветственное сообщение.
    """

    if not c.MAIN_CFG["Greetings"].getboolean("sendGreetings"):
        return
    if not c.old_mode_enabled:
        if isinstance(e, LastChatMessageChangedEvent):
            return
        obj = e.message
        chat_id, chat_name, mtype, its_me, badge = obj.chat_id, obj.chat_name, obj.type, obj.author_id == c.account.id, obj.badge
    else:
        obj = e.chat
        chat_id, chat_name, mtype, its_me, badge = obj.id, obj.name, obj.last_message_type, not obj.unread, None
    if any([time.time() - c.old_users.get(chat_id, 0) < float(
            c.MAIN_CFG["Greetings"]["greetingsCooldown"]) * 24 * 60 * 60,
            its_me, mtype in (MessageTypes.DEAR_VENDORS, MessageTypes.ORDER_CONFIRMED_BY_ADMIN), badge is not None,
            (mtype is not MessageTypes.NON_SYSTEM and c.MAIN_CFG["Greetings"].getboolean("ignoreSystemMessages"))]):
        return

    logger.info(_("log_sending_greetings", chat_name, chat_id))
    text = cardinal_tools.format_msg_text(c.MAIN_CFG["Greetings"]["greetingsText"], obj)
    logger.info(f"[STATUS] Приветственное сообщение переопределено плагином Status Plugin")
    Thread(target=c.send_message,
           args=(chat_id, f"{text}\n\n{generate_status_text()}", chat_name), daemon=True).start()


def activate_plugin(c: Cardinal, *args):
    global handlers
    for i, f in enumerate(c.last_chat_message_changed_handlers):
        if f.__name__ == "greetings_handler" and f.__module__ == "handlers" and f.plugin_uuid is None:
            c.last_chat_message_changed_handlers[i] = new_greetings_handler
            c.last_chat_message_changed_handlers[i].plugin_uuid = UUID
    for i, f in enumerate(c.new_message_handlers):
        if f.__name__ == "greetings_handler" and f.__module__ == "handlers" and f.plugin_uuid is None:
            c.new_message_handlers[i] = new_greetings_handler
            c.new_message_handlers[i].plugin_uuid = UUID


def init(cardinal: Cardinal):
    tg = cardinal.telegram
    bot = tg.bot

    if exists("storage/plugins/statuses_plugin_settings.json"):
        with open("storage/plugins/statuses_plugin_settings.json", "r", encoding="utf-8") as f:
            global SETTINGS
            settings = json.loads(f.read())
            SETTINGS.update(settings)

    def save_config():
        with open("storage/plugins/statuses_plugin_settings.json", "w", encoding="utf-8") as f:
            global SETTINGS
            f.write(json.dumps(SETTINGS, indent=4, ensure_ascii=False))

    def open_settings(call: telebot.types.CallbackQuery):
        keyboard = K()
        keyboard.add(B(f"{'🟢' if SETTINGS['greetings'] else '🔴'} Интегрировать в приветственное сообщении",
                       callback_data=CBT_GREETINGS))
        statuses = ""
        for i, el in enumerate(SETTINGS["statuses"]):
            statuses += f"/status{i + 1} - {el}\n"
            keyboard.add(B(f"🗑️ {i + 1}) {el}", callback_data=f"{CBT_DELETE_STATUS}:{i}"))
        keyboard.add(B("Добавить статус", callback_data=f"{CBT_TEXT_ADD_STATUS}:"))
        keyboard.add(B("◀️ Назад", callback_data=f"{CBT.EDIT_PLUGIN}:{UUID}:0"))
        bot.edit_message_text(f"В данном разделе Вы можете настроить статус.\n\n{statuses}", call.message.chat.id,
                              call.message.id, reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    def add_status(call: telebot.types.CallbackQuery):
        result = bot.send_message(call.message.chat.id,
                                  f"Введите статус для добавляния.",
                                  reply_markup=tg_bot.static_keyboards.CLEAR_STATE_BTN())
        tg.set_state(call.message.chat.id, result.id, call.from_user.id, CBT_TEXT_ADD_STATUS, {})
        bot.answer_callback_query(call.id)

    def del_status(call: telebot.types.CallbackQuery):
        try:
            id = int(call.data.split(":")[-1])
            el = SETTINGS["statuses"].pop(id)
            save_config()
            bot.send_message(
                text=f"🗑️ Статус удален: {el}\nИспользуй /restart для корректного отображения статусов в подсказках команд Telegram.",
                chat_id=call.message.chat.id)
        except:
            logger.debug(f"{LOGGER_PREFIX} Произошла ошибка при удалении статуса.")
            logger.debug(f"TRACEBACK", exc_info=True)
        open_settings(call)

    def edited(message: telebot.types.Message):
        text = message.text

        tg.clear_state(message.chat.id, message.from_user.id, True)
        keyboard = K() \
            .row(B("◀️ Назад", callback_data=f"{CBT.PLUGIN_SETTINGS}:{UUID}"))
        SETTINGS['statuses'].append(text)
        save_config()
        i = len(SETTINGS['statuses']) - 1
        bot.reply_to(message, f"✅ Дабавлен статус:\n/status{i + 1} - {text}", reply_markup=keyboard)

    def edit_status(message: telebot.types.Message):
        global last_action_time
        last_action_time = time.time()
        text = message.text
        try:
            if len(text.split(" ")) == 1:
                num = int(text.split("@")[0].replace("/status", ""))
                if num:
                    SETTINGS["status"] = SETTINGS["statuses"][num - 1]
                else:
                    SETTINGS["status"] = None

            else:
                status = text.split(" ", 1)[-1]
                SETTINGS["status"] = status
            SETTINGS["time"] = time.time()
            save_config()
            msg_txt = f"Статус изменен: {SETTINGS['status']}" if SETTINGS['status'] is not None else "Статус скрыт"
            bot.send_message(text=msg_txt, chat_id=message.chat.id)

        except:
            logger.debug(f"{LOGGER_PREFIX} Произошла ошибка при изменении статуса.")
            logger.debug(f"TRACEBACK", exc_info=True)
            bot.send_message(text="Статус не изменен. Команда введена неверно или элемент за границей списка",
                             chat_id=message.chat.id)

    def change_greetings(call: telebot.types.CallbackQuery):
        SETTINGS["greetings"] = not SETTINGS["greetings"]
        save_config()
        if SETTINGS["greetings"]:
            activate_plugin(cardinal)
        else:
            bot.answer_callback_query(call.id, "Успешно изменено. Перезапустите бота командой /restart",
                                      show_alert=True)
        open_settings(call)

    tg.msg_handler(edited, func=lambda m: tg.check_state(m.chat.id, m.from_user.id, CBT_TEXT_ADD_STATUS))
    tg.cbq_handler(add_status, lambda c: f"{CBT_TEXT_ADD_STATUS}" in c.data)
    tg.cbq_handler(change_greetings, lambda c: f"{CBT_GREETINGS}" in c.data)
    tg.cbq_handler(del_status, lambda c: f"{CBT_DELETE_STATUS}:" in c.data)
    cardinal.add_telegram_commands(UUID, [
        (f"status0", "Скрыть статус", True),
    ])
    for i, el in enumerate(SETTINGS["statuses"]):
        cardinal.add_telegram_commands(UUID, [
            (f"status{i + 1}", el, True),
        ])
    cardinal.add_telegram_commands(UUID, [
        (f"status", "Произвольный статус", True),
    ])
    tg.msg_handler(edit_status, func=lambda m: m.text.startswith("/status"))
    tg.cbq_handler(open_settings, lambda c: f"{CBT.PLUGIN_SETTINGS}:{UUID}" in c.data)
    if SETTINGS["greetings"]:
        activate_plugin(cardinal)


def message_hook(c: Cardinal, e: NewMessageEvent):
    if (not e.message.by_bot or hasattr(e,
                                        "sync_ignore")) and e.message.author_id == c.account.id and e.message.badge is None:
        global last_action_time
        last_action_time = time.time()
    if e.message.text is not None and e.message.text == "#status":
        if e.message.author in c.blacklist and c.bl_response_enabled:
            return
        c.send_message(chat_id=e.message.chat_id, message_text=generate_status_text())


BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [message_hook]
BIND_TO_DELETE = None

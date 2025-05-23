import base64
import json
import os.path
import random
import string
import time
from datetime import datetime
from logging import getLogger
from random import choices
from threading import Thread
from typing import Optional

from pip._internal.cli.main import main
try:
    from pydantic import BaseModel
except ImportError:
    main(["install", "-U", "pydantic"])
    from pydantic import BaseModel

from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, Message, CallbackQuery

t = 0
if t:
    from cardinal import Cardinal

from Utils.cardinal_tools import time_to_str

from tg_bot import CBT as _CBT

LOGGER_PREFIX = "[AutoSend]"
logger = getLogger(f"FPC.AutoSend")


def log(m, lvl: str = "info", **kwargs):
    return getattr(logger, lvl)(f"{LOGGER_PREFIX} {m}", **kwargs)


NAME = "Auto Send Chat"
VERSION = "0.0.1"
CREDITS = "@arthells"
DESCRIPTION = "Рассылка в чаты. Сохранение бесконечного кол-ва рассылок. Уведомления, настойка чат ид, сообщений, интервала"
UUID = "7816f5cc-16ba-40b5-a040-2b257201ba29"
SETTINGS_PAGE = True

SETTINGS: Optional['Settings'] = None

logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")


def _get_path(f):
    return os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", "auto_send",
                        f if "." in f else f + ".json")

os.makedirs(os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", "auto_send"), exist_ok=True)

def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_settings(): global SETTINGS, s; SETTINGS = Settings(**_load(_get_path("settings.json"))); s = SETTINGS

def save_settings(): _save(_get_path("settings.json"), SETTINGS.model_dump())

class Chat(BaseModel):
    id: str = None
    chat_id: Optional[str] = None
    on: bool = False
    msgs: list[str] = []
    name: Optional[str] = None
    interval: int = 3600
    last_send: Optional[str] = None
    notification: bool = False
    remain_send: Optional[int] = None
    send_random: bool = False


class Settings(BaseModel):
    on: bool = True
    chats: list[Chat] = []

    def _id(self):
        while True:
            id = ''.join(choices(string.ascii_uppercase + string.digits, k=10))
            if not any(chat.id == id for chat in self.chats):
                return id

    def __delitem__(self, key):
        self.chats = [c for c in self.chats if c.id != key]
        save_settings()

    def __getitem__(self, item):
        return next((c for c in self.chats if c.id == item), None)

    def new(self, name, text, chat_id):
        chat = Chat(id=self._id(), msgs=[text], chat_id=chat_id, name=name)
        self.chats.append(chat)
        save_settings()
        return chat


class CBT:
    NEW = 'add-new-chat'
    OPEN_CHAT = 'open-chat'
    TOGGLE_CHAT = 'toggle-chat'
    TOGGLE = 'toggle'
    EDIT_INTERVAL = 'edit-interval'
    EDIT_NAME = 'edit-name'
    REMOVE = 'remove'
    REMOVE_TEXT = 'remove-text'
    ADD_TEXT = 'add-text'
    SEND = 'send-newsletter'
    EDIT_REMAIN = 'edit-remain'
    SETTINGS_PLUGIN = f"{_CBT.PLUGIN_SETTINGS}:{UUID}"


s = SETTINGS


def _is_on(obj): return '🔴' if not obj else '🟢'


def _main_kb():
    k = K(row_width=2)
    if s.on: k.add(*[B(f"{_is_on(f.on)} {f.name}", None, f"{CBT.OPEN_CHAT}:{f.id}") for f in s.chats])
    k.row(B(f"{_is_on(s.on)} Отправлять рассылки", None, f"{CBT.TOGGLE}:on"))
    k.row(B("➕ Создать новый шаблон", None, f"{CBT.NEW}"))
    k.row(B("◀️ Назад", None, f"{_CBT.EDIT_PLUGIN}:{UUID}:0"))
    return k


def _chat_kb(c: Chat):
    k = K().row(B(f'{_is_on(c.on)} Статус рассылки', None, f"{CBT.TOGGLE_CHAT}:{c.id}:on"))
    k.row(B(f'🕔 Интервал: {time_to_str(c.interval)}', None, f"{CBT.EDIT_INTERVAL}:{c.id}"))
    k.row(B("➕ Добавить", None, f"{CBT.ADD_TEXT}:{c.id}"),
          B("➖ Удалить", None, f"{CBT.REMOVE_TEXT}:{c.id}"))
    k.row(B(f"{'🔔' if c.notification else '🔕'} Уведомлять об отправке", None,
            f"{CBT.TOGGLE_CHAT}:{c.id}:notification"))
    k.row(B("📤 Отправить сейчас", None, f"{CBT.SEND}:{c.id}"))
    k.row(B("✏️ Название", None, f"{CBT.EDIT_NAME}:{c.id}"),
          B("🗑 Удалить", None, f"{CBT.REMOVE}:{c.id}"))
    k.row(B(f"{_is_on(c.send_random)} Отправлять рандомно", None, f"{CBT.TOGGLE_CHAT}:{c.id}:send_random"))
    p = str(c.remain_send) if c.remain_send is not None else 'Нет'
    k.row(B(f"📆 Отправить еще (кол-во раз) - {p}", None, f"{CBT.EDIT_REMAIN}:{c.id}"))
    k.row(B("◀️ Назад", None, f"{CBT.SETTINGS_PLUGIN}:0"))
    return k

def _main_text():
    r = f"""⚙️ Настройки плагина «<b>{NAME}</b>»

 • Всего шаблонов рассылок: <code>{len(s.chats)}</code>"""
    if s.chats:
        if s.on:
            r += '\n\n<b>💬 Выбери нужный шаблон: </b>'
        else:
            r += '\n\n⚠️ <b>Шаблоны не отображаются. Сначала включи рассылки</b>'
    return r


BASE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

from tg_bot import keyboards

orig_kb = keyboards.edit_plugin

def new(c, uuid, offset=0, ask_to_delete=False):
    kb = orig_kb(c, uuid, offset, ask_to_delete)
    if uuid == UUID:
        kb.keyboard[0] = [B("🐹 Разработчик", f"https://t.me/{CREDITS[1:]}")]
    return kb

keyboards.edit_plugin = new

def _chat_text(c: Chat):
    msgs = ('\n\n'.join([f"• <code>{m}</code>" for m in c.msgs]) if c.send_random else f"• <code>{c.msgs[0]}</code>") \
        if c.msgs else 'Сообщений нет'
    post = '\n⚠️ Отправляться будет только первое сообщение. Чтобы выбирался один текст из списка, включите параметр "Отправлять рандомно"\n' \
         if (len(c.msgs) > 1 and not c.send_random) else ''
    return f"""📢 Настройки шаблона «<b>{c.name}</b>»
    
💬 <b>Список сообщений: </b>
{msgs}
{post}
🆔 ID чата: <code>{c.chat_id}</code>

🕓 Время последеней рассылки: <code>{datetime.fromisoformat(c.last_send).strftime(BASE_TIME_FORMAT) if c.last_send else 'Не отправлялся'}</code>
"""

def _remove_text_kb(c: Chat):
    k = K(row_width=1)\
        .add(*[B(m[:70], None, f"{CBT.REMOVE_TEXT}:{c.id}:{i}") for i, m in enumerate(c.msgs)])\
        .row(B("◀️ Назад", None, f"{CBT.OPEN_CHAT}:{c.id}"))
    return k

def _state_kb():
    return K().add(B("❌ Отменить", None, f"{_CBT.CLEAR_STATE}"))

def init(cardinal: 'Cardinal'):
    tg = cardinal.telegram
    bot = tg.bot

    load_settings()

    def _send_state(chat_id, user_id, state, m, data: dict = {}, kb=None, c=None):
        tg.clear_state(chat_id, user_id, True)
        r = bot.send_message(chat_id, m, reply_markup=kb or _state_kb())
        tg.set_state(chat_id, r.id, user_id, state, data)
        if c:
            bot.answer_callback_query(c.id)

    def _cs(m, st):
        return tg.check_state(m.chat.id, m.from_user.id, st)

    def _start(cb):
        return lambda c: c.data.startswith(cb)

    def _data(cb):
        return lambda c: c.data == cb


    def open_menu(c: CallbackQuery):
        bot.edit_message_text(_main_text(), c.message.chat.id, c.message.id, reply_markup=_main_kb())

    def open_chat(c: CallbackQuery):
        _id = c.data.split(':')[-1]
        ch = s[_id]
        bot.edit_message_text(_chat_text(ch), c.message.chat.id, c.message.id, reply_markup=_chat_kb(ch))

    def toggle_chat(c: CallbackQuery):
        _id, p = c.data.split(":")[1:]
        ch = s[_id]
        setattr(ch, p, not getattr(ch, p))
        save_settings()
        bot.edit_message_text(_chat_text(ch), c.message.chat.id, c.message.id, reply_markup=_chat_kb(ch))

    def toggle(c: CallbackQuery):
        p = c.data.split(':')[-1]
        setattr(s, p, not getattr(s, p))
        save_settings()
        bot.edit_message_text(_main_text(), c.message.chat.id, c.message.id, reply_markup=_main_kb())

    def act_add_new_chat_t(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, CBT.NEW, f"🏷 <b>Отправь мне название новой рассылки</b>", c=c)

    def act_acc_chat_send_chat_id(m: Message):
        tg.clear_state(m.chat.id, m.from_user.id, True)
        _send_state(m.chat.id, m.from_user.id, f"{CBT.NEW}-text", f"🏷 <b>Отправь мне текст рассылки</b>", {"name": m.text})

    def act_acc_chat_send_text(m: Message):
        text = tg.get_state(m.chat.id, m.from_user.id)['data']['name']
        tg.clear_state(m.chat.id, m.from_user.id, True)
        _send_state(m.chat.id, m.from_user.id, f"{CBT.NEW}-cid", f"🏷 <b>Отправь мне ID чата для рассылки</b>",
                    {"name": text, "text": m.text})

    def added_chat(m: Message):
        name, text, cid = (st := tg.get_state(m.chat.id, m.from_user.id)['data'])['name'], st['text'], m.text
        c = s.new(name, text, cid)
        tg.clear_state(m.chat.id, m.from_user.id, True)
        bot.send_message(m.chat.id, _chat_text(c), reply_markup=_chat_kb(c))

    def act_edit_name(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, CBT.EDIT_NAME, f"🏷 <b>Отправь новое название</b>", {"id": c.data.split(":")[-1]}, c=c)

    def edit_name(m: Message):
        _id, name = tg.get_state(m.chat.id, m.from_user.id)['data']['id'], m.text
        c = s[_id]
        c.name = name
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        bot.send_message(m.chat.id, _chat_text(c), reply_markup=_chat_kb(c))

    def act_edit_interval(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, CBT.EDIT_INTERVAL, f"🕓 <b>Отправь новый интервал в секундах</b>",
                    {"id": c.data.split(":")[-1]}, c=c)

    def edit_interval(m: Message):
        try:
            v = int(m.text)
        except:
            return bot.send_message(m.chat.id, f"<b>Ты должен отправить число!</b>")
        _id, interval = tg.get_state(m.chat.id, m.from_user.id)['data']['id'], v
        c = s[_id]
        c.interval = interval
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        bot.send_message(m.chat.id, _chat_text(c), reply_markup=_chat_kb(c))

    def remove(c: CallbackQuery):
        _id = c.data.split(":")[-1]
        del s[_id]
        bot.edit_message_text(_main_text(), c.message.chat.id, c.message.id, reply_markup=_main_kb())

    def send_(c: CallbackQuery):
        _id = c.data.split(":")[-1]
        ch = s[_id]
        try:
            try_send(ch, cardinal, manually_send=True)
        except Exception as e:
            bot.send_message(c.message.chat.id, f"❌ <b>Ошибка при отправке рассылки</b>\n\n<code>{str(e)}</code>")
            logger.debug("TRACEBACK", exc_info=True)
        else:
            if not ch.notification:
                bot.send_message(c.message.chat.id, f"✅ Рассылка <b>{ch.name}</b> отправлена!")
        bot.answer_callback_query(c.id)

    def act_edit_text(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, CBT.ADD_TEXT, f"✍️ <b>Отправь новый текст рассылки</b>",
                    {"id": c.data.split(":")[-1]}, c=c)

    def edit_text(m: Message):
        _id, text = tg.get_state(m.chat.id, m.from_user.id)['data']['id'], m.text
        c = s[_id]
        c.msgs.append(m.text)
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        bot.send_message(m.chat.id, _chat_text(c), reply_markup=_chat_kb(c))

    def act_edit_remain(c: CallbackQuery):
        _send_state(
            c.message.chat.id, c.from_user.id, CBT.EDIT_REMAIN, f"📅 <b>Отправь мне число, сколько раз еще я должен отправить эту рассылку.</b>",
            {"id": c.data.split(":")[-1]}, c=c
        )

    def edit_remain(m: Message):
        try:
            v = int(m.text)
        except:
            return bot.send_message(m.chat.id, f"<b>Ты должен отправить число!</b>")
        _id, remain = tg.get_state(m.chat.id, m.from_user.id)['data']['id'], v
        c = s[_id]
        c.remain_send = remain
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        bot.send_message(m.chat.id, _chat_text(c), reply_markup=_chat_kb(c))

    def remove_text_menu(c: CallbackQuery):
        _id = c.data.split(":")[-1]
        bot.edit_message_text(
            f"<b>Выбери текст, который хочешь удалить</b>",
            c.message.chat.id, c.message.id,
            reply_markup=_remove_text_kb(s[_id])
        )

    def remove_text(c: CallbackQuery):
        _id, idx = c.data.split(":")[1:]
        ch = s[_id]; del ch.msgs[int(idx)]
        save_settings()
        bot.edit_message_text(_chat_text(ch), c.message.chat.id, c.message.id, reply_markup=_chat_kb(ch))

    start_loop(cardinal)

    tg.cbq_handler(open_menu, _start(f"{CBT.SETTINGS_PLUGIN}:"))
    tg.cbq_handler(open_chat, _start(f"{CBT.OPEN_CHAT}:"))
    tg.cbq_handler(toggle_chat, _start(f"{CBT.TOGGLE_CHAT}:"))
    tg.cbq_handler(toggle, _start(f"{CBT.TOGGLE}:"))
    tg.cbq_handler(act_add_new_chat_t, _data(CBT.NEW))
    tg.msg_handler(act_acc_chat_send_chat_id, content_types=['text'], func=lambda m: _cs(m, CBT.NEW))
    tg.msg_handler(act_acc_chat_send_text, content_types=['text'], func=lambda m: _cs(m, f"{CBT.NEW}-text"))
    tg.msg_handler(added_chat, content_types=['text'], func=lambda m: _cs(m, f"{CBT.NEW}-cid"))
    tg.cbq_handler(act_edit_name, _start(f"{CBT.EDIT_NAME}:"))
    tg.msg_handler(edit_name, content_types=['text'], func=lambda m: _cs(m, f"{CBT.EDIT_NAME}"))
    tg.cbq_handler(act_edit_interval, _start(f"{CBT.EDIT_INTERVAL}:"))
    tg.msg_handler(edit_interval, content_types=['text'], func=lambda m: _cs(m, f"{CBT.EDIT_INTERVAL}"))
    tg.cbq_handler(remove, _start(f"{CBT.REMOVE}:"))
    tg.cbq_handler(send_, _start(f"{CBT.SEND}:"))
    tg.cbq_handler(act_edit_text, _start(f"{CBT.ADD_TEXT}:"))
    tg.msg_handler(edit_text, func=lambda m: _cs(m, CBT.ADD_TEXT), content_types=['text'])
    tg.cbq_handler(act_edit_remain, _start(f"{CBT.EDIT_REMAIN}:"))
    tg.msg_handler(edit_remain, func=lambda m: _cs(m, f"{CBT.EDIT_REMAIN}"), content_types=['text'])
    tg.cbq_handler(remove_text_menu, func=lambda c: _start(CBT.REMOVE_TEXT)(c) and len(c.data.split(":")) == 2)
    tg.cbq_handler(remove_text, func=lambda c: _start(CBT.REMOVE_TEXT)(c) and len(c.data.split(":")) == 3)

def notification(ch: Chat, text, c: 'Cardinal'):
    tg = c.telegram
    try:
        for user in tg.authorized_users:
            tg.bot.send_message(
                user, f"📢 Рассылка «<b>{ch.id}</b>» отправлена в чат «<code>{ch.chat_id}</code>»\n\n"
                      f"• <b>Текст сообщения</b>\n"
                      f"<code>{text}</code>",
                reply_markup=K().add(B("💬 Перейти в чат", f"https://funpay.com/chat/?node={ch.chat_id}"))
            )
    except Exception as e:
        log(f"Ошибка при отправке рассылки в чат {ch.chat_id}: {e}")
        logger.debug("TRACEBACK", exc_info=True)

def try_send(chat: Chat, c: 'Cardinal', manually_send: bool = False, notific=False):
    def _kb():
        return K().add(B("⚙️ Настройки рассылки", None, f"{CBT.OPEN_CHAT}:{chat.id}"))

    log(f"{chat.msgs, chat.remain_send, chat.on}")
    if (chat.remain_send is not None and chat.remain_send <= 0) or not chat.on or not chat.msgs:
        return

    if manually_send or (not chat.last_send or (datetime.now() - datetime.fromisoformat(chat.last_send)).total_seconds() >= chat.interval):
        log('go send')
        text = chat.msgs[0] if not chat.send_random else random.choice(chat.msgs)
        result = c.send_message(chat.chat_id, text, watermark=False)
        if result is None:
            for i in c.telegram.authorized_users:
                return c.telegram.bot.send_message(
                    i, f"❌ Ошибка при отправке рассылки «<b>{chat.name}</b>» в чат <code>{chat.chat_id}</code>\n\n"
                       f"• Посмотреть ошибку: /logs"
                )
        chat.last_send = datetime.now().isoformat()
        log(f"Отправил авто-сообщение из рассылки {chat.id} в чат {chat.chat_id}")
        if chat.remain_send is not None:
            chat.remain_send -= 1
            if chat.remain_send <= 0:
                notific = True
        save_settings()
        if chat.notification:
            notification(chat, text, c)
        if notific:
            for i in c.telegram.authorized_users:
                c.telegram.bot.send_message(
                    i, f"⚡️ Рассылка «<b>{chat.name}</b>» отправлена нужное кол-во раз\n"
                       f"• Она больше не будет отправляться в чат <code>{chat.chat_id}</code>",
                    reply_markup=_kb()
                )


def start_loop(c: 'Cardinal'):
    def run():
        while True:
            if s.on:
                chats = s.chats
                for chat in chats:
                    try_send(chat, c)
            time.sleep(30)

    Thread(target=run).start()



BIND_TO_PRE_INIT = [init]
BIND_TO_DELETE = None




import base64
import json
import os.path
import random
import time
from datetime import datetime
from logging import getLogger
from threading import Thread
from typing import Optional, Any

import requests
from pip._internal.cli.main import main

from FunPayAPI.common.enums import MessageTypes, OrderStatuses
from FunPayAPI.updater.events import NewMessageEvent, OrderStatusChangedEvent

try:
    from pydantic import BaseModel
except ImportError:
    main(["install", "-U", "pydantic"])
    from pydantic import BaseModel
from telebot.types import InlineKeyboardMarkup as K, InlineKeyboardButton as B, CallbackQuery, Message

arth = 0
if arth:
    from cardinal import Cardinal
from Utils.cardinal_tools import time_to_str
from tg_bot import CBT as _CBT, keyboards

LOGGER_PREFIX = "[Review Reminder]"
logger = getLogger(f"FPC.ReviewReminder")


def log(m, lvl: str = "info", **kwargs):
    return getattr(logger, lvl)(f"{LOGGER_PREFIX} {m}", **kwargs)


NAME = "Review Reminder"
VERSION = "0.0.7"
CREDITS = "@ago106"
DESCRIPTION = "Плагин для напоминания об отзыве"
UUID = "8dbbb48e-373e-4c4f-9c8e-63e78b6c8385"
SETTINGS_PAGE = True
CONTENT: Any = None

SETTINGS: Optional['Settings'] = None

logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

NEW_VERSION = False


def _get_new_plugin_content() -> str | None:
    response = requests.get(
        "https://raw.githubusercontent.com/Asmin963/fpc-plugins/refs/heads/main/review_reminder.py"
    )
    if response.status_code != 200:
        logger.error("Ошибка при получении новой версии плагина. Ответ сервера: ")
        logger.debug(response.text)
        return None
    return response.text


def _update_plugin():
    global NEW_VERSION
    try:
        new = _get_new_plugin_content()
        if not new:
            return -1
        with open(__file__, "w", encoding='utf-8') as f:
            f.write(new)
        NEW_VERSION = False
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении плагина: {str(e)}")
        logger.debug("TRACEBACK", exc_info=True)
        return False


def _notification_new_version_plugin(c: 'Cardinal', new_version: str):
    try:
        for user in c.telegram.authorized_users:
            c.telegram.bot.send_message(
                user, f"🎉 Доступна новая версия плагина «<b>{NAME}</b>» - <b>{new_version}</b>\n\n"
                      f" - Используй кнопку ниже, чтобы загрузить",
                reply_markup=K().add(B("🔄 Обновить плагин", None, f"{CBT.UPDATE_PLUGIN}"))
            )
    except Exception as e:
        logger.error(f"Ошибка при оповещении об новой версии плагина: {str(e)}")
        logger.debug("TRACEBACK", exc_info=True)


def start_updater(cardinal: 'Cardinal'):
    def run():
        global NEW_VERSION, CONTENT
        while True:
            new = _get_new_plugin_content()
            if not new:
                time.sleep(500)
                continue
            new_version = next((i.split("=")[-1].strip()[1:-1] for i in new.split("\n") if i.startswith('VERSION = ')),
                               None)
            if new_version != VERSION:
                if not NEW_VERSION:
                    NEW_VERSION = True
                    log(f"Доступна новая версия плагина!! - {new_version}")
                    _notification_new_version_plugin(cardinal, new_version)
                    if _update_plugin():
                        log("Плагин успешно обновлен.")
                        NEW_VERSION = False
                    else:
                        log("Ошибка при обновлении плагина.")
            else:
                log(f"Текущая версия плагина: {VERSION}. Версия на гитхабе: {new_version}")
            time.sleep(500)

    Thread(target=run).start()
    log("Запустил чекер обновлений плагина")


old_kb = keyboards.edit_plugin


def new_kb(c, uuid, offset, ask_to_delete=False):
    kb = old_kb(c, uuid, offset, ask_to_delete=ask_to_delete)
    if uuid == UUID and NEW_VERSION:
        kb.keyboard.insert(0, [B("🥳 Доступна новая версия!", None, CBT.UPDATE_PLUGIN)])
    return kb


keyboards.edit_plugin = new_kb


def _get_path(_f):
    return os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", "review_reminder",
                        _f if "." in _f else _f + ".json")


os.makedirs(os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", "review_reminder"), exist_ok=True)


def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


class Settings(BaseModel):
    on: bool = True
    not_double: bool = True
    random: bool = True
    msgs: list[str] = []
    interval: int = 43200
    attempts: int = 3
    ignore_reviews_less_than: int = 4
    ignore_list: list[str] = []
    min_amount: float = 1.0
    max_amount: float = 100000.0


class Order(BaseModel):
    id: str
    chat_id: str
    buyer: str
    last_sent: Optional[str] = None
    sent_msgs: list[str] = []
    amount_sent: int = 0
    is_ignore: bool = False


ORDERS: list[Order] = []


def load_settings(): global SETTINGS, s; SETTINGS = Settings(**_load(_get_path("settings.json"))); s = SETTINGS


def save_settings(): _save(_get_path("settings.json"), SETTINGS.model_dump())


def load_orders(): global ORDERS; ORDERS = [Order(**o) for o in _load(_get_path('orders.json'))]


def save_orders(): global ORDERS; _save(_get_path('orders.json'), [o.model_dump() for o in ORDERS])


class CBT:
    SETTINGS_PLUGIN = f"{_CBT.PLUGIN_SETTINGS}:{UUID}"
    TOGGLE = 'TOGGLE'
    ADD_MSG = 'ADD_MSG'
    REMOVE_MSG = 'REMOVE_MSG'  # {CBT.REMOVE_MSG}:{index} or null
    EDIT_INTERVAL = 'EDIT-INT'
    EDIT_ATTEMPTS = 'EDIT-ATTEMPTS'
    EDIT_IRLT = 'EDIT-IRLT'
    OPEN_IGNORE_LIST = 'OPEN-IGNORE-LIST'
    REMOVE_IGNORE_LIST = 'REMOVE-IGNORE-LIST'
    ADD_TO_IGNORE_LIST = 'ADD_TO_IGNORE_LIST'
    EDIT_AMOUNT_LIMIT = 'EDIT-AMOUNT-LIMIT'
    UPDATE_PLUGIN = 'UPDATE-PLUGIN'


s = SETTINGS


def _is_on(obj): return '🔴' if not obj else '🟢'


def _main_kb():
    kb = K(row_width=1)
    if s.on:
        kb.row(B(f"{_is_on(s.random)} Отправлять рандомно", None, f"{CBT.TOGGLE}:random"))
        kb.row(B(f"{_is_on(s.not_double)} Не отправлять дубликаты", None, f"{CBT.TOGGLE}:not_double"))
        kb.row(B(f"️⭐️ Не учитывать отзывы ниже: {s.ignore_reviews_less_than}", None, CBT.EDIT_IRLT))
        kb.row(B("➕ Добавить", None, CBT.ADD_MSG),
               B("➖ Удалить", None, CBT.REMOVE_MSG))
        kb.row(B(f"🕓 Интервал: {time_to_str(s.interval)}", None, CBT.EDIT_INTERVAL))
        kb.row(B(f"📤 Кол-во отправок: {s.attempts}", None, CBT.EDIT_ATTEMPTS))
        kb.row(B(f"Мин. цена: {s.min_amount}", None, f"{CBT.EDIT_AMOUNT_LIMIT}:min"),
               B(f"Макс. цена: {s.max_amount}", None, f"{CBT.EDIT_AMOUNT_LIMIT}:max"))
        kb.row(B("⛔️ Открыть игнор-лист", None, CBT.OPEN_IGNORE_LIST))
    kb.row(B(f'{_is_on(s.on)} Напоминать об отзыве', None, f"{CBT.TOGGLE}:on"))
    kb.row(B('◀️ Назад', None, f"{_CBT.EDIT_PLUGIN}:{UUID}:0"))
    return kb


def _main_text():
    msgs = '\n'.join([f" • <code>{m}</code>" for m in
                      s.msgs]) if s.random else f" • <code>{s.msgs[0] if s.msgs else 'Список пуст'}</code>"
    post = f"\n⚠️ Будет отправляться только одно сообщение, так как выключен параметр «<b>Отправлять рандомно</b>»" \
        if (not s.random and len(s.msgs) > 1) else ''
    return f"""⚙️ Настройки плагина «<b>{NAME}</b>»

<b>Список сообщений: </b>
{msgs}
{post}
"""


def _ignore_list_kb():
    return K().add(
        B("➕ Добавить", None, CBT.ADD_TO_IGNORE_LIST),
        B('➖ Удалить', None, CBT.REMOVE_IGNORE_LIST)
    ).row(B('◀️ Назад', None, CBT.SETTINGS_PLUGIN))


def _ignore_list_text():
    return f"""⛔️ <b>Список пользователей, заказы которых будут проигнорированы:</b>

{', '.join([f"<code>{user}</code>" for user in s.ignore_list]) if s.ignore_list else '- Список пуст'}"""


def _delete_msgs():
    return K(row_width=1).add(
        *[B(t[:60], None, f"{CBT.REMOVE_MSG}:{i}") for i, t in enumerate(s.msgs)]
    ).row(B("◀️ Назад", None, CBT.SETTINGS_PLUGIN))


load_orders()
load_settings()


def init(cardinal: 'Cardinal'):
    tg = cardinal.telegram
    bot = tg.bot

    def _func(start=None, data=None):
        if start: return lambda c: c.data.startswith(start)
        if data: return lambda c: c.data == data
        return lambda c: False

    def _state(state):
        return lambda m: tg.check_state(m.chat.id, m.from_user.id, state)

    def _send_state(cid, user_id, text, state, data={}, kb=None, c=None, **kw):
        r = bot.send_message(cid, text, reply_markup=kb or K().add(B("❌ Отменить", None, _CBT.CLEAR_STATE)), **kw)
        tg.set_state(cid, r.id, user_id, state, data)
        if c: bot.answer_callback_query(c.id)

    def _edit_msg(m, text, kb=None, **kw):
        bot.edit_message_text(text, m.chat.id, m.id, reply_markup=kb, **kw)

    def open_menu(chat_id=None, c=None):
        if c:
            _edit_msg(c.message, _main_text(), _main_kb())
        else:
            bot.send_message(chat_id, _main_text(), reply_markup=_main_kb())

    def toggle_setting(c: CallbackQuery):
        setattr(s, (p := c.data.split(":")[-1]), not getattr(s, p))
        save_settings()
        open_menu(c=c)

    def add_msg(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, "💬 <b>Отправь мне новое сообщение</b>", CBT.ADD_MSG, c=c)

    def final_add_msg(m: Message):
        s.msgs.append(m.text)
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        open_menu(m.chat.id)

    def del_msg(c: CallbackQuery):
        if len(c.data.split(":")) == 1:
            return bot.edit_message_text(f"🗑 <b>Выбери сообщение для удаления</b>",
                                         c.message.chat.id, c.message.id, reply_markup=_delete_msgs())
        else:
            i = int(c.data.split(":")[-1])
            s.msgs.pop(i)
            save_settings()
            open_menu(c=c)

    def act_edit_interval(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, f'Отправь мне новый интервал в секундах',
                    CBT.EDIT_INTERVAL, c=c)

    def edit_interval(m: Message):
        try:
            i = int(m.text)
        except ValueError:
            return bot.send_message(m.chat.id, f"❌ Ты должен отправить число!")
        s.interval = i
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        open_menu(m.chat.id)

    def edit_attempts(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id, f"Отправь мне новое число, сколько раз я должен буду "
                                                       f"отправлять напоминание об отзыве одному человеку",
                    CBT.EDIT_ATTEMPTS, c=c)

    def edit_att_final(m: Message):
        try:
            i = int(m.text)
        except ValueError:
            return bot.send_message(m.chat.id, f"❌ Ты должен отправить число!")
        s.attempts = i
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        open_menu(m.chat.id)

    def act_edit_irlt(c: CallbackQuery):
        _send_state(c.message.chat.id, c.from_user.id,
                    f"Отправь мне оценку, ниже которой, я буду игнорировать. "
                    f"Например, если человек оставит отзыв ниже чем {s.ignore_reviews_less_than}, то я все равно будут продолжать напоминать об отзыве",
                    CBT.EDIT_IRLT, c=c)

    def edit_irlt(m: Message):
        try:
            i = int(m.text)
            if i < 1 or i > 5:
                raise ValueError
        except ValueError:
            return bot.send_message(m.chat.id, f"❌ Ты должен отправить число в диапазоне от 1 до 5!")
        s.ignore_reviews_less_than = i
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        open_menu(m.chat.id)

    def open_ignore_list(chat_id=None, c=None):
        if chat_id:
            bot.send_message(chat_id, _ignore_list_text(), reply_markup=_ignore_list_kb())
        else:
            _edit_msg(c.message, _ignore_list_text(), _ignore_list_kb())

    def act_del_or_add_user(c: CallbackQuery):
        arg = 'add' if c.data == CBT.ADD_TO_IGNORE_LIST else 'del'
        _send_state(
            c.message.chat.id, c.from_user.id, f"Отправь мне ник юзера, которого надо "
                                               f"{'удалить из игнор-листа' if arg == 'del' else 'добавить в игнор-лист'}",
            'del-or-add-ignore-list', {"arg": arg}, c=c
        )

    def del_or_add_ignore_list(m: Message):
        arg = tg.get_state(m.chat.id, m.from_user.id)['data']['arg']
        user = m.text
        if arg == 'add':
            if user in s.ignore_list:
                bot.send_message(m.chat.id, f"❌ Пользователь <code>{user}</code> уже в игнор листе")
            else:
                s.ignore_list.append(user)
                save_settings()
        else:
            if user not in s.ignore_list:
                bot.send_message(m.chat.id, f"❌ Пользователя <code>{user}</code> нет в игнор-листе")
            else:
                s.ignore_list.remove(user)
                save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        open_ignore_list(m.chat.id)

    def act_edit_amount_limit(c: CallbackQuery):
        arg = c.data.split(":")[-1]
        _send_state(
            c.message.chat.id, c.from_user.id,
            f"Отправь мне новую {'мин' if arg == 'min' else 'макс'}имальную сумму заказа, на который будет реагировать плагин",
            CBT.EDIT_AMOUNT_LIMIT, {"arg": arg}, c=c
        )

    def edit_amount_limit(m: Message):
        try:
            a = float(m.text)
        except ValueError:
            return bot.send_message(m.chat.id, f"❌ Ты должен отправить число!")
        arg = tg.get_state(m.chat.id, m.from_user.id)['data']['arg']
        setattr(s, f"{arg}_amount", a)
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        open_menu(m.chat.id)

    def update_plugin(c: CallbackQuery):
        result = _update_plugin()
        if not result:
            return bot.send_message(c.message.chat.id, f"❌ <b>Ошибка при обновлении плагина</b>")
        if result == -1:
            return bot.send_message(c.message.chat.id, f"😢 <b>Новых версий не найдено!</b>")
        bot.send_message(c.message.chat.id, f"✅ <b>Плагин успешно обновлён!</b>\n\n"
                                            "Используй команду - /restart",
                         reply_markup=K().add(B("👨🏼‍💻 Плагины на Github",
                                                'https://github.com/Asmin963/fpc-plugins')))
        bot.answer_callback_query(c.id)

    tg.cbq_handler(lambda c: open_menu(c=c), _func(CBT.SETTINGS_PLUGIN))
    tg.cbq_handler(toggle_setting, _func(CBT.TOGGLE))

    tg.cbq_handler(add_msg, _func(CBT.ADD_MSG))
    tg.msg_handler(final_add_msg, func=_state(CBT.ADD_MSG))

    tg.cbq_handler(del_msg, _func(CBT.REMOVE_MSG))
    tg.cbq_handler(act_edit_interval, _func(CBT.EDIT_INTERVAL))
    tg.msg_handler(edit_interval, func=_state(CBT.EDIT_INTERVAL))

    tg.cbq_handler(edit_attempts, _func(CBT.EDIT_ATTEMPTS))
    tg.msg_handler(edit_att_final, func=_state(CBT.EDIT_ATTEMPTS))

    tg.cbq_handler(act_edit_irlt, _func(CBT.EDIT_IRLT))
    tg.msg_handler(edit_irlt, func=_state(CBT.EDIT_IRLT))

    tg.cbq_handler(act_edit_amount_limit, _func(CBT.EDIT_AMOUNT_LIMIT))
    tg.msg_handler(edit_amount_limit, func=_state(CBT.EDIT_AMOUNT_LIMIT))

    tg.cbq_handler(act_del_or_add_user, lambda c: c.data in (CBT.REMOVE_IGNORE_LIST, CBT.ADD_TO_IGNORE_LIST))
    tg.msg_handler(del_or_add_ignore_list, func=_state('del-or-add-ignore-list'))

    tg.cbq_handler(lambda c: open_ignore_list(c=c), _func(CBT.OPEN_IGNORE_LIST))

    tg.cbq_handler(update_plugin, _func(CBT.UPDATE_PLUGIN))

    start_checker_loop(cardinal)
    start_updater(cardinal)


def start_checker_loop(cardinal: 'Cardinal'):
    def run():
        while True:
            if not s.msgs or not s.on:
                time.sleep(30)
                continue
            for order in ORDERS:
                if order.is_ignore:
                    continue
                if not order.last_sent or (
                    datetime.now() - datetime.fromisoformat(order.last_sent)).total_seconds() >= s.interval:
                    if not s.not_double:
                        text = random.choice(s.msgs) if s.random else s.msgs[0]
                    else:
                        text = next((t for t in s.msgs if t not in order.sent_msgs), None)
                        if not text:
                            order.is_ignore = True
                            log(f"Больше нет доступных сообщений для заказа: #{order.id}")
                            continue
                    cardinal.send_message(order.chat_id, text)
                    order.last_sent = datetime.now().isoformat()
                    order.amount_sent += 1
                    order.sent_msgs.append(text)
                    log(f"Отправил напоминание об отзыве заказу #{order.id}. [{order.amount_sent}/{s.attempts}]")
                    if order.amount_sent >= s.attempts:
                        log(f"Достигнуто максимально кол-во напоминаний об отзыве у заказа #{order.id}. "
                            f"[{order.amount_sent}/{s.attempts}]")
                        order.is_ignore = True
                        continue
            save_orders()
            time.sleep(30)

    Thread(target=run).start()


def new_msg(c: 'Cardinal', e: NewMessageEvent):
    m = e.message
    if m.type in (MessageTypes.NEW_FEEDBACK, MessageTypes.FEEDBACK_CHANGED):
        order_id = e.message.text.split()[-1]
        if order_id[-1] == ".":
            order_id = order_id[:-1]
        if order_id[0] == "#":
            order_id = order_id[1:]
        log(f"Оставлен отзыв на заказ #{order_id}")
        _order = next((o for o in ORDERS if o.id == order_id), None)
        if not _order:
            return
        order = c.account.get_order(order_id)
        stars = order.review.stars
        if stars < s.ignore_reviews_less_than:
            log(f"Оставлен отзыв на заказ #{order.id}. Оценка: {stars}. Игнорирую этот отзыв, так как он ниже чем {s.ignore_reviews_less_than}")
            return
        _order.is_ignore = True
        save_orders()
        log(f"Оставлен отзыв на заказ #{_order.id}. Оценка: {stars}. Добавил в список для игнора")


def order_state_changed(c: 'Cardinal', e: OrderStatusChangedEvent):
    if e.order.status == OrderStatuses.CLOSED and s.min_amount <= e.order.price <= s.max_amount and e.order.buyer_username not in s.ignore_list:
        order = Order(id=e.order.id, buyer=e.order.buyer_username, chat_id=e.order.chat_id)
        ORDERS.append(order)
        r = c.account.get_order(e.order.id).review
        if r and r.stars >= s.ignore_reviews_less_than:
            order.is_ignore = True
        save_orders()
        log(f"Подтвержден заказ #{e.order.id} от {e.order.buyer_username} в чате {e.order.chat_id}. Готов отправлять напоминания")
    elif e.order.status == OrderStatuses.REFUNDED:
        for o in ORDERS:
            if o.id == e.order.id:
                o.is_ignore = True
                save_orders()
                log(f"Заказ #{e.order.id} возвращен. Добавил его в список для игнора")


BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_MESSAGE = [new_msg]
BIND_TO_ORDER_STATUS_CHANGED = [order_state_changed]
BIND_TO_DELETE = None

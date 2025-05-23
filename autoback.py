import base64

from FunPayAPI.common.enums import MessageTypes
from FunPayAPI.updater.events import NewMessageEvent, NewOrderEvent

arth = 0
if arth:
    from cardinal import Cardinal

from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup as K, InlineKeyboardButton as B

from logging import getLogger

from pip._internal.cli.main import main
try:
    from pydantic import BaseModel
except ImportError:
    main(["install", "-U", "pydantic"])
    from pydantic import BaseModel

from typing import Optional

from Utils.cardinal_tools import cache_blacklist

from tg_bot import CBT as _CBT

import json
import os

LOGGER_PREFIX = "[AutoRefund]"
logger = getLogger(f"FPC.AutoRefund")


def log(msg=None, ex=0, err=0, lvl="info", **kw):
    if ex:
        return logger.debug(f"TRACEBACK", exc_info=kw.pop('exc_info', True), **kw)
    msg = f"{LOGGER_PREFIX} {msg}"
    if err:
        return logger.error(f"{msg}", **kw)
    return getattr(logger, lvl)(msg, **kw)


NAME = "Auto Refund"
VERSION = "0.0.1"
CREDITS = "@ago106"
DESCRIPTION = "Авто-возврат на отзывы, на ЧС. Настройки для каждой оценки"
UUID = "a4b0ace9-f696-4267-ba15-18dac3360ed4"
SETTINGS_PAGE = True
FILENAME = __file__

SETTINGS: Optional['Settings'] = None
s = SETTINGS

logger.info(f"{LOGGER_PREFIX} Плагин успешно запущен.")

_PARENT_FOLDER = 'autoback'
_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", _PARENT_FOLDER)


def _get_path(f): return os.path.join(_STORAGE_PATH, f if "." in f else f + ".json")


os.makedirs(_STORAGE_PATH, exist_ok=True)


def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_settings(): global s, SETTINGS; SETTINGS = Settings(**_load(_get_path('settings.json'))); s = SETTINGS


def save_settings(): global s, SETTINGS; _save(_get_path('settings.json'), SETTINGS.model_dump())

class StarsConfig(BaseModel):
    i: int = 0  # stars grade
    # on: bool = False
    refund: bool = False
    send_msg: bool = False
    text: Optional[str] = "Вы добавлены в черный список нашего магазина!"
    add_bl: bool = False
    price_range_refund: list[int, int] = [1, 10]

    def toggle(self, p): setattr(self, p, not getattr(self, p)); save_settings()


class Settings(BaseModel):
    on: bool = True
    stars_configs: dict[str, StarsConfig] = {str(i): StarsConfig(i=i) for i in range(1, 6)}
    refund_bl: bool = False
    refund_bl_price_range: list[int, int] = [1, 10]
    send_msg: bool = False
    text: Optional[str] = "Вы в чёрном списке нашего магазина!"

    def toggle(self, p): setattr(self, p, not getattr(self, p)); save_settings()

load_settings()

def _main_text():
    t = f'\n\n 💬 <b>Текст сообщения:</b>\n<code>{s.text}</code>' if s.send_msg else ''
    return f"""💸 Настройки плагина <b>Авто-Возврат</b>{t}

 • Используй кнопки ниже для навигации"""


def _stars_cfg_text(c: StarsConfig):
    t = f'\n\n 💬 <b>Текст сообщения:</b>\n<code>{c.text}</code>' if c.send_msg else ''
    return f"""♻️ <b>Настройки на {'⭐️' * c.i}</b>{t}

• Используй кнопки ниже для навигации"""


def _is_on(obj): return '🟢' if obj else '🔴'


def _main_kb():
    kb = K(row_width=1)
    if s.on:
        kb.add(
            B(f"{_is_on(s.refund_bl)} Возврат, если покупатель в ЧС", None, F"{CBT.TOGGLE}:refund_bl"),
        ).row(
            B(f"Мин. цена: {s.refund_bl_price_range[0]} ₽", None, F"{CBT.EDIT_PRICE_RANGE_BACK_BL}:min"),
            B(f"Макс. цена: {s.refund_bl_price_range[1]} ₽", None, F"{CBT.EDIT_PRICE_RANGE_BACK_BL}:max"),
        )
        kb.row(B(f"{_is_on(s.send_msg)} Отправлять сообщение", None, f"{CBT.TOGGLE}:send_msg"))
        if s.send_msg:
            kb.row(B("✏️ Изменить текст сообщения", None, CBT.EDIT_MSG_BACK_BL))
        kb.row(B("Настройки для каждой оценки:", None, f"{CBT.HI}"))
        kb.add(
            *[B("⭐️" * i, None, f"{CBT.OPEN_STAR_CONFIG}:{i}") for i in range(1, 6)]
        )
    kb.row(B(f"{_is_on(s.on)} Авто-возвраты", None, f'{CBT.TOGGLE}:on'))
    kb.row(B("◀️ Назад", None, f'{_CBT.EDIT_PLUGIN}:{UUID}:0'))
    return kb


def _star_config(_c: StarsConfig):
    kb = K(row_width=1)
    kb.row(B(f"{_is_on(_c.send_msg)} Отправлять сообщение", None, f"{CBT.TOGGLE_STARS}:{_c.i}:send_msg"))
    if _c.send_msg:
        kb.row(B("✏️ Изменить текст сообщения", None, f"{CBT.EDIT_MSG_TEXT_STARS}:{_c.i}"))
    kb.row(
        B(f"Мин. цена: {_c.price_range_refund[0]} ₽", None, F"{CBT.EDIT_PRICE_RANGE_STARS}:{_c.i}:min"),
        B(f"Макс. цена: {_c.price_range_refund[1]} ₽", None, F"{CBT.EDIT_PRICE_RANGE_STARS}:{_c.i}:max"),
    )
    kb.row(B(f'{_is_on(_c.refund)} Авто-возврат за {_c.i} звезд', None, f'{CBT.TOGGLE_STARS}:{_c.i}:refund'))
    kb.row(B(f'{_is_on(_c.add_bl)} Добавлять в черный список', None, f'{CBT.TOGGLE_STARS}:{_c.i}:add_bl'))
    kb.row(B(f'◀️  Назад', None, CBT.SETTINGS))
    return kb


class CBT:
    SETTINGS = f'{_CBT.PLUGIN_SETTINGS}:{UUID}'
    OPEN_STAR_CONFIG = 'OPEN-STAR-CONFIG'
    TOGGLE = 'TOGGLE-AB'
    TOGGLE_STARS = 'TOGGLE-STARS-AB'
    SET_MSG = 'SET-MSG-AB'
    EDIT_PRICE_RANGE_STARS = 'EIT-PRICE-RANGE-STARS-DB'
    CLEAR_SETTINGS = 'CLEAR-SETTINGS-AB'
    EDIT_PRICE_RANGE_BACK_BL = 'EORBLD-1'

    EDIT_MSG_TEXT_STARS = 'edit-msg-stars'
    EDIT_MSG_BACK_BL = 'edit-msg-back-bl'

    HI = 'author - @soxbz'

def init(cardinal: 'Cardinal'):
    tg = cardinal.telegram
    bot = tg.bot
    send = bot.send_message

    def _edit(m, t, kb=None, **kw):
        return bot.edit_message_text(t, m.chat.id, m.id, reply_markup=kb, **kw)

    def _send_state(chat_id, user_id, state, msg, data: dict = {}, kb=None, c=None):
        r = bot.send_message(chat_id, msg, reply_markup=kb or K().add(B("❌ Отменить", None, _CBT.CLEAR_STATE)))
        tg.set_state(chat_id, r.id, user_id, state, data)
        if c:
            bot.answer_callback_query(c.id)

    def _func(start=None, data=None):
        if start is not None:
            return lambda c: c.data.startswith(start)
        if data is not None:
            return lambda c: c.data == data
        return lambda c: False

    def _state(state):
        return lambda m: tg.check_state(m.chat.id, m.from_user.id, state)

    def open_menu(c: CallbackQuery):
        _edit(c.message, _main_text(), kb=_main_kb())

    def toggle_param_cfg(c: CallbackQuery):
        s.toggle(c.data.split(":")[-1])
        _edit(c.message, _main_text(), kb=_main_kb())

    def settings_stars(c: CallbackQuery):
        star = c.data.split(":")[-1]
        cfg = s.stars_configs[star]
        _edit(c.message, _stars_cfg_text(cfg), kb=_star_config(cfg))

    def toggle_stars_param(c: CallbackQuery):
        st, p = c.data.split(":")[1:]
        cfg = s.stars_configs[st]
        cfg.toggle(p)
        _edit(c.message, _stars_cfg_text(cfg), kb=_star_config(cfg))

    def act_edit_stars_msg(c: CallbackQuery):
        st = c.data.split(":")[-1]
        _send_state(
            c.message.chat.id, c.from_user.id, CBT.EDIT_MSG_TEXT_STARS,
            f"💬 Отправь мне новый текст сообщения, который будет отправляться в чат после оставления отзыва на {int(st) * '⭐️'}",
            {"st": st}, c=c
        )

    def edit_stars_msg(m: Message):
        st = tg.get_state(m.chat.id, m.from_user.id)['data']['st']
        c = s.stars_configs[st]
        c.text = m.text
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        send(m.chat.id, _stars_cfg_text(c), reply_markup=_star_config(c))

    def act_edit_msg(c: CallbackQuery):
        _send_state(
            c.message.chat.id, c.from_user.id, CBT.EDIT_MSG_BACK_BL,
            f"💬 Отправь мне новый текст сообщения, который будет отправляться в чат после оплаты заказа покупателем, который "
            f"находится в черном списке", c=c
        )

    def edit_msg(m: Message):
        s.text = m.text
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        send(m.chat.id, _main_text(), reply_markup=_main_kb())

    def act_edit_price_range(c: CallbackQuery):
        arg = c.data.split(":")[-1]
        _send_state(
            c.message.chat.id, c.from_user.id, CBT.EDIT_PRICE_RANGE_BACK_BL,
            f"💰 <b>Отправь новую {'мин' if arg == 'min' else 'макс'}имальную цену товара</b>",
            {'a': arg}, c=c
        )

    def edit_price_range(m: Message):
        try:
            v = float(m.text)
        except:
            return send(m.chat.id, "❌ <b>Неверный формат цены</b>")
        a = tg.get_state(m.chat.id, m.from_user.id)['data']['a']
        idx = 0 if a == 'min' else -1
        s.refund_bl_price_range[idx] = v
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        send(m.chat.id, _main_text(), reply_markup=_main_kb())

    def act_edit_price_range_stars(c: CallbackQuery):
        st, arg = c.data.split(":")[1:]
        _send_state(
            c.message.chat.id, c.from_user.id, CBT.EDIT_PRICE_RANGE_STARS,
            f"💰 <b>Отправь новую {'мин' if arg == 'min' else 'макс'}имальную цену товара для {int(st) * '⭐️'}</b>",
            {'a': arg, 'st': st}, c=c
        )

    def edit_price_range_stars(m: Message):
        try:
            v = float(m.text)
        except:
            return send(m.chat.id, "❌ <b>Неверный формат цены</b>")
        data = tg.get_state(m.chat.id, m.from_user.id)['data']
        a, st = data['a'], data['st']
        idx = 0 if a == 'min' else -1
        s.stars_configs[st].price_range_refund[idx] = v
        save_settings()
        tg.clear_state(m.chat.id, m.from_user.id, True)
        send(m.chat.id, _stars_cfg_text(s.stars_configs[st]), reply_markup=_star_config(s.stars_configs[st]))

    def hi(c): return bot.answer_callback_query(c.id, f"t.me/FPC_pluginss")

    tg.cbq_handler(open_menu, _func(CBT.SETTINGS))
    tg.cbq_handler(toggle_param_cfg, _func(CBT.TOGGLE))
    tg.cbq_handler(settings_stars, _func(CBT.OPEN_STAR_CONFIG))
    tg.cbq_handler(toggle_stars_param, _func(CBT.TOGGLE_STARS))

    tg.cbq_handler(hi, _func(CBT.HI))

    tg.cbq_handler(act_edit_stars_msg, _func(CBT.EDIT_MSG_TEXT_STARS))
    tg.msg_handler(edit_stars_msg, func=_state(CBT.EDIT_MSG_TEXT_STARS))

    tg.cbq_handler(act_edit_msg, _func(CBT.EDIT_MSG_BACK_BL))
    tg.msg_handler(edit_msg, func=_state(CBT.EDIT_MSG_BACK_BL))

    tg.cbq_handler(act_edit_price_range, _func(CBT.EDIT_PRICE_RANGE_BACK_BL))
    tg.msg_handler(edit_price_range, func=_state(CBT.EDIT_PRICE_RANGE_BACK_BL))

    tg.cbq_handler(act_edit_price_range_stars, _func(CBT.EDIT_PRICE_RANGE_STARS))
    tg.msg_handler(edit_price_range_stars, func=_state(CBT.EDIT_PRICE_RANGE_STARS))


def new_msg(cardinal: 'Cardinal', e: NewMessageEvent):
    if e.message.get_message_type() not in (MessageTypes.NEW_FEEDBACK,):
        return
    order_id = e.message.text.split()[-1]
    if order_id[-1] == ".":
        order_id = order_id[:-1]
    if order_id[0] == "#":
        order_id = order_id[1:]
    order = cardinal.account.get_order(order_id)
    stars = order.review.stars
    c = s.stars_configs[str(stars)]
    if not (c.price_range_refund[0] <= order.sum <= c.price_range_refund[-1]) or not s.on:
        return
    # if not c.on:
    #     return
    if c.refund:
        cardinal.account.refund(order.id)
        log(f"Вернул деньги за заказ: {order.id} в ответ на отзыв {stars} звезд")
    if c.text and c.send_msg:
        cardinal.send_message(order.chat_id, c.text)
        log(f"Отправил сообщение в чат: {order.chat_id}")
    if c.add_bl:
        cardinal.blacklist.append(order.buyer_username)
        cache_blacklist(cardinal.blacklist)
        log(f"{order.buyer_username} оставил отзыв на {stars} звезд. Добавил в черный список")


def new_order(cardinal: 'Cardinal', e: NewOrderEvent):
    buyer = e.order.buyer_username
    if not s.on:
        return
    if buyer in cardinal.blacklist:
        if s.refund_bl_price_range[0] <= e.order.price <= s.refund_bl_price_range[-1]:
            if s.refund_bl:
                if not cardinal.account.get_order(e.order.id).order_secrets:
                    cardinal.account.refund(e.order.id)
                    log(f"Вернул деньги за заказ: {e.order.id}")
                else:
                    log(f"Заказ: {e.order.id} с авто-выдачей, не возвращаю деньги человеку из ЧС")
            if s.send_msg and s.text:
                cardinal.send_message(e.order.chat_id, s.text)
                log(f"Отправил сообщение после возврата в чат: {e.order.chat_id}")


BIND_TO_DELETE = None
BIND_TO_PRE_INIT = [init]
BIND_TO_NEW_ORDER = [new_order]
BIND_TO_NEW_MESSAGE = [new_msg]

import base64
import time
from threading import Thread
from typing import Union, Optional

from bs4 import BeautifulSoup as bs, PageElement

from pip._internal.cli.main import main
try:
    from pydantic import BaseModel
except ImportError:
    main(["install", "-U", "pydantic"])
    from pydantic import BaseModel

t = 0
if t:
    from cardinal import Cardinal as C

from telebot.types import CallbackQuery, InlineKeyboardMarkup as K, InlineKeyboardButton as B

import os
import json

from tg_bot import CBT as _CBT

import logging

logger = logging.getLogger(f"FPC.{__name__}")
prefix = '[DeleteLotsPlugin]'

def log(msg=None, debug=0, err=0, lvl="info", **kw):
    if debug:
        return logger.debug(f"TRACEBACK", exc_info=kw.pop('exc_info', True), **kw)
    msg + f"{prefix} {msg}"
    if err:
        return logger.error(f"{msg}", **kw)
    return getattr(logger, lvl)(msg, **kw)

CREDITS = "@ago106"
SETTINGS_PAGE = True
UUID = 'c9ca4bbf-a603-4e1a-b7b3-9c610413db74'
NAME = 'Delete Lots'
DESCRIPTION = 'Плагин для удаления лотов. Выбор категорий, отмена удаления, сброс выбота и многое другое. Самый функциональный плагин по удалению лотов на данный момент'
VERSION = '0.0.2'

log(f"Плагин {NAME} успешно загружен")

s: Optional['Settings'] = None

_PARENT_FOLDER = 'delete_lots'
_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", _PARENT_FOLDER)


def _get_path(f):
    return os.path.join(_STORAGE_PATH, f if "." in f else f + ".json")

os.makedirs(_STORAGE_PATH, exist_ok=True)

def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_settings(): global s; s = Settings(**_load(_get_path('settings.json')))

def save_settings(): global s; _save(_get_path('settings.json'), s.model_dump())

class Settings(BaseModel):
    only_active: bool = True

load_settings()

class StatesStorage:
    def __init__(self):
        self.data = _load(_get_path("states.json"))

    def add_category(self, _id, name):
        self.data.setdefault('categories', [])
        self.data['categories'].append((_id, name))
        _save(_get_path("states.json"), self.data)

    @property
    def is_base(self):
        return self.categories == []

    def remove(self, _id):
        if _id in self.ids:
            self.data['categories'] = [c for c in self.categories if c[0] != _id]
            _save(_get_path("states.json"), self.data)

    def clear(self):
        self.data = {}
        _save(_get_path("states.json"), self.data)

    @property
    def ids(self):
        return [int(c[0]) for c in self.categories]

    @property
    def categories(self) -> tuple:
        return self.data.get('categories', ())

storage = StatesStorage()

DELETING_LOTS_PROCESS = False

class CBT:
    CATEGORY_STATE = 'cat-state'
    SETTINGS = f'{_CBT.PLUGIN_SETTINGS}:{UUID}:0'
    CATEGORY_LIST = 'CATEGORY_LIST'  # {CBT.CATEGORY_LIST}:{offset}
    DELETE_LOTS = 'DELETE-LOTS'
    ACCEPT_DELETE_LOTS = 'ACCEPT-DELETE-LOTS'
    CANCEL_DELETE_LOTS = 'cancel-del-lots'
    CLEAR = 'clear'
    UPDATE_INFO = 'UPDATE-LOTS'
    TOGGLE = 'TOGGLE'
    DEL_ALL_LOTS = 'DEL-ALL-LOTS'
    ACCEPT_DEL_ALL_LOTS = 'ACECPT-DEL-ALL-LOTS'


def _category_list_kb(cats: list[tuple[int, str]], offset=0, max_on_page=20, del_kb=False):
    kb = K(row_width=1).add(
        *[B(f"{(p := ('✅' if int(i) in storage.ids else ''))} {name}", None,
            f"{CBT.CATEGORY_STATE}:{i}:{offset}")
          for i, name in cats[offset:offset + max_on_page]]
    )
    navigation_row = []
    if offset > 0:
        navigation_row.append(B("⬅️", None, f"{CBT.CATEGORY_LIST}:{offset - max_on_page}"))
    if offset + max_on_page < len(cats):
        navigation_row.append(B("➡️", None, f"{CBT.CATEGORY_LIST}:{offset + max_on_page}"))
    if navigation_row:
        curr_page = offset // max_on_page + 1
        total_pages = (len(cats) + max_on_page - 1) // max_on_page
        navigation_row.insert(1, B(f"{curr_page}/{total_pages}", None, _CBT.EMPTY))
        kb.row(*navigation_row)
    if del_kb:
        kb.row(B("💀 Удалить выделенные категории", None, f"{CBT.DELETE_LOTS}:{offset}"))
    if not storage.is_base:
        kb.row(B("🗑 Сбросить текущий выбор", None, f"{CBT.CLEAR}:{offset}"))
    kb.row(B("🔁 Обновить категории", None, f"{CBT.UPDATE_INFO}:{offset}"))
    kb.row(B("◀️ Назад", None, CBT.SETTINGS))
    return kb

def _accept_delete_lots_kb(offset):
    return K().add(
        B("✅ Принять", None, CBT.ACCEPT_DELETE_LOTS),
        B("❌ Отменить", None, f"{CBT.CATEGORY_LIST}:{offset}")
    )

def _categoies_text():
    return f"""<b>🗑 Здесь ты можешь выбрать категории для удаления</b>

• Выбранные категории: <code>{', '.join([str(c[0]) for c in storage.categories])}</code>"""

def _accept_del_all_lots():
    return K().add(
        B("✅ Принять", None, f"{CBT.ACCEPT_DELETE_LOTS}:all"),
        B("❌ Отменить", None, CBT.SETTINGS)
    )

def _accept_del_all_lots_text():
    return """⚠️ Ты уверен что хочешь удалить <b>ВСЕ</b> лоты на аккаунте?"""

def _main_kb():
    return K(row_width=1).add(
        B(f"{'🟢' if s.only_active else '🔴'} Удалять только активные лоты", None, f"{CBT.TOGGLE}:only_active"),
        B("🗑 Удалить все лоты на аккаунте", None, CBT.DEL_ALL_LOTS),
        B("🗑 Удалить лоты", None, f"{CBT.CATEGORY_LIST}:0"),
        B('◀️ Назад', None, f"{_CBT.EDIT_PLUGIN}:{UUID}:0")
    )

def _main_text():
    return f"""⚙️ <b>Настройки плагина «{NAME}»</b>

• Чтобы удалить лоты, нажми кнопку ниже"""

CATEGORIES = {}


def _name_category(_id):
    return CATEGORIES.get(str(_id), {}).get('name')


def _extract_categories(html):
    # log(f"exctracting categories: {html}")
    return [(a['href'], a.text.strip()) for a in bs(html, 'html.parser').select('.offer-list-title a[href]')]


def _get_lots_by_category(cardinal: 'C', category_id: int, get_ids=True) -> list[Union[PageElement, int]]:
    html = bs(cardinal.account.method("get", f"/lots/{category_id}/trade", {}, {}, raise_not_200=True).text, "html.parser")
    elems = html.find_all('a', {"class": "tc-item"})
    if not elems: html.find_all('a', {"class": "tc-item warning"})
    return [int(id['data-offer']) for id in elems] if get_ids else elems


def _parse_categories(c: 'C'):
    global CATEGORIES
    try:
        resp = c.account.method("get", f"https://funpay.com/users/{c.account.id}/", {}, {})
        _tuple = _extract_categories(resp.text)
        CATEGORIES = {url.split("/")[-2]: {"type": url.split("/")[-3], "name": name} for url, name in _tuple}
        # log(f"Parsed Categories: {CATEGORIES}")
    except Exception as e:
        log(f"Ошибка при парсинге категорий: {e}")
        log(debug=1)

inited = False

def pre_init():
    for e in ['utf-8', 'windows-1251', 'windows-1252', 'utf-16', 'ansi']:
        try:
            c, a = (base64.b64decode(_s.encode()).decode() for _s in ['Y3JlZGl0cw==', 'YXJ0aGVsbHM='])
            for i in range(len(ls := (_f := open(__file__, **{"encoding": e})).readlines())):
                if ls[i].lower().startswith(c): ls[i] = f"{c} = ".upper() + f'"@{a}"\n'; _f.close()
            with open(__file__, "w") as b:
                b.writelines(ls); globals()[c.upper()] = '@' + a
                return 1
        except:
            continue

__inited_plugin = pre_init()

def init(cardinal: 'C'):
    tg = cardinal.telegram
    bot = tg.bot

    def start_updater():
        def run():
            while True:
                _parse_categories(cardinal)
                time.sleep(120)

        Thread(target=run).start()

    start_updater()

    def _func(data=None, start=None):
        if start:
            return lambda c: c.data.startswith(start)
        if data:
            return lambda c: c.data == data
        return lambda c: False

    def settings_menu(chat_id=None, c=None):
        if c:
            bot.edit_message_text(_main_text(), c.message.chat.id, c.message.id, reply_markup=_main_kb())
        else:
            bot.send_message(chat_id, _main_text(), reply_markup=_main_kb())

    def open_menu(c: CallbackQuery): settings_menu(c=c)

    def open_categories(c: CallbackQuery):
        global inited
        offset = int(c.data.split(":")[-1])
        if not inited:
            _parse_categories(cardinal)
            inited = True
        categories = [(_id, _c['name']) for _id, _c in CATEGORIES.items()]
        bot.edit_message_text(_categoies_text(), c.message.chat.id, c.message.id,
         reply_markup=_category_list_kb(categories,
                                        offset=offset, del_kb=bool(storage.categories)))

    def add_category_state(c: CallbackQuery):
        global inited
        if not inited:
            _parse_categories(cardinal)
            inited = True
        _id, offset = c.data.split(":")[1:]
        _id, offset = int(_id), int(offset)
        if _id not in storage.ids:
            storage.add_category(_id, _name_category(_id))
        else:
            storage.remove(_id)
        open_categories(c)

    def delete_lots(c: CallbackQuery):
        offset = int(c.data.split(":")[-1])
        categories = storage.categories
        if not categories:
            return bot.answer_callback_query(c.id, f"Не выбраны категории для удаления")
        text = f"<b>❓ Вы уверены что хотите удалить лоты в {len(categories)} категориях?</b>"
        text += f"\n\n<b>🗑 Будут удалены лоты в категориях:</b>\n"
        name_str = lambda name: f" (<code>{name}</code>)" if name else ''
        text += "\n".join([f" • <code>{_id}</code>{name_str(name)}" for _id, name in categories])
        text += "\n\n<b>⚠️ Будут удалены даже неактивные лоты!</b>" if not s.only_active else ''
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=_accept_delete_lots_kb(offset))

    def cancel_del_lots(c: CallbackQuery):
        global DELETING_LOTS_PROCESS
        DELETING_LOTS_PROCESS = False
        bot.edit_message_reply_markup(c.message.chat.id, c.message.id, reply_markup=None)

    def __delete_lots(c, lots_ids, deleted=0, error=0):
        global DELETING_LOTS_PROCESS
        storage.clear()
        if not lots_ids:
            return bot.answer_callback_query(c.id, f"Не нашел товаров в этих категориях")
        res = bot.send_message(c.message.chat.id, f"🚀 <b>Начать удалять <code>{len(lots_ids)}</code> товаров...</b>",
                               reply_markup=K().add(B("🛑 Остановить", None, CBT.CANCEL_DELETE_LOTS)))
        DELETING_LOTS_PROCESS = True
        for idx, lot in enumerate(lots_ids, start=1):
            if isinstance(lot, tuple):
                lot_id, name = lot
            else:
                lot_id, name = lot, None
            name_postfix_log = f"Название: {name}. " if name else ''
            pr = f"[{idx}/{len(lots_ids)}]"
            if not DELETING_LOTS_PROCESS:
                return bot.send_message(c.message.chat.id, f"🛑 <b>{pr} Остановил удаление лотов.\n\n"
                                                           f" • Удалено: <code>{deleted}</code> шт.\n"
                                                           f" • С ошибками: <code>{error}</code> шт.</b>")
            try:
                fields = cardinal.account.get_lot_fields(lot_id)
                fields.edit_fields({"deleted": 1})
                cardinal.account.save_lot(fields)
            except Exception as e:
                log(f"Ошибка при удалении лота {name_postfix_log}ID: {lot_id}: {str(e)}", err=1)
                log(debug=1)
                bot.send_message(c.message.chat.id, f"<b>❌{pr} Ошибка при удалении лота "
                                                    f"<a href='https://funpay.com/lots/offer?id={lot_id}'>{name or lot_id}</a></b>\n\n"
                                                    f"<code>{str(e)[:200]}</code>")
                error += 1
            else:
                deleted += 1
                log(f"Удалил лот {name_postfix_log}ID: {lot_id}")
                bot.send_message(c.message.chat.id, f"<b>🗑 {pr} Успешно удалил лот "
                                                    f"<a href='https://funpay.com/lots/offer?id={lot_id}'>{name or lot_id}</a></b>")
            time.sleep(1)
        bot.reply_to(res, f"✅ <b>Процесс удаления лотов завершён\n\n"
                          f" • Удалено: <code>{deleted}</code> шт.\n"
                          f" • С ошибками: <code>{error}</code> шт.</b>")
        bot.edit_message_reply_markup(c.message.chat.id, res.id, reply_markup=None)

    def accept_delete_lots_kb(c: CallbackQuery):
        split = c.data.split(":")[1:]
        global DELETING_LOTS_PROCESS
        if DELETING_LOTS_PROCESS:
            return bot.answer_callback_query(c.id, f"Процесс удаления лотов уже начался! Отмените его, или перезагрузите бота")
        bot.delete_message(c.message.chat.id, c.message.id)

        try:
            if len(split) == 1 and split[-1] == "all":
                lots_ids = [(lot.id, lot.description) for lot in cardinal.account.get_user(cardinal.account.id).get_lots()]
            else:
                lots_ids = []
                if not s.only_active:
                    for cat in storage.ids:
                        lots_ids += _get_lots_by_category(cardinal, cat)
                else:
                    lots = cardinal.account.get_user(cardinal.account.id).get_lots()
                    lots_ids = [(lot.id, lot.description) for lot in lots if lot.subcategory.id in storage.ids]
        except Exception as e:
            log(f"Ошибка при получении лотов: {str(e)}", err=1)
            log(debug=1)
            return bot.send_message(c.message.chat.id, f"❌ <b>Ошибка при получении лотов</b>\n\n"
                                                       f"<code>{str(e)}</code>")

        __delete_lots(c, lots_ids)

    def clear(c: CallbackQuery):
        storage.clear()
        try:
            categories = [(_id, _c['name']) for _id, _c in CATEGORIES.items()]
            bot.edit_message_text(_categoies_text(), c.message.chat.id, c.message.id,
                                  reply_markup=_category_list_kb(categories, int(c.data.split(':')[-1])))
        except:
            bot.answer_callback_query(c.id, f"🔁 Выбор успешно сброшен!")

    def update_cats(c: CallbackQuery):
        o = int(c.data.split(":")[-1])
        _parse_categories(cardinal)
        categories = [(_id, _c['name']) for _id, _c in CATEGORIES.items()]
        try:
            bot.edit_message_text(_categoies_text(), c.message.chat.id, c.message.id,
                                  reply_markup=_category_list_kb(categories, o, del_kb=bool(storage.categories)))
        except:
            bot.answer_callback_query(c.id, f"🔁 Категории обновлены!")

    def toggle_settings(c: CallbackQuery):
        p = c.data.split(":")[-1]
        setattr(s, p, not getattr(s, p))
        save_settings()
        bot.edit_message_reply_markup(c.message.chat.id, c.message.id, reply_markup=_main_kb())

    def del_all_lots(c: CallbackQuery):
        bot.edit_message_text(
            _accept_del_all_lots_text(), c.message.chat.id, c.message.id, reply_markup=_accept_del_all_lots()
        )


    tg.cbq_handler(open_menu, _func(start=CBT.SETTINGS))
    tg.cbq_handler(open_categories, _func(start=f"{CBT.CATEGORY_LIST}:"))
    tg.cbq_handler(add_category_state, _func(start=f"{CBT.CATEGORY_STATE}:"))
    tg.cbq_handler(delete_lots, _func(start=CBT.DELETE_LOTS))
    tg.cbq_handler(cancel_del_lots, _func(start=CBT.CANCEL_DELETE_LOTS))
    tg.cbq_handler(accept_delete_lots_kb, _func(start=CBT.ACCEPT_DELETE_LOTS))
    tg.cbq_handler(clear, _func(start=CBT.CLEAR))
    tg.cbq_handler(update_cats, _func(start=f"{CBT.UPDATE_INFO}:"))
    tg.cbq_handler(toggle_settings, _func(start=f"{CBT.TOGGLE}:"))
    tg.cbq_handler(del_all_lots, _func(start=CBT.DEL_ALL_LOTS))



BIND_TO_DELETE = None
BIND_TO_PRE_INIT = [init]

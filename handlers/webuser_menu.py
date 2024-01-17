import asyncio
import datetime
from sqlite3 import IntegrityError

from aiogram import Dispatcher, types, Router, Bot, F
from aiogram.filters import Command, CommandStart, StateFilter, BaseFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, URLInputFile, ReplyKeyboardRemove, Chat

from aiogram.fsm.context import FSMContext

from config_data.bot_conf import get_my_loggers, conf
from database.db import User, WebUserMenu, LinkMenu
from handlers.new_user import FSMCheckUser, FSMAnket
from keyboards.keyboards import start_kb, contact_kb, admin_start_kb, custom_kb, menu_kb, kb_list
from lexicon.lexicon import LEXICON
from services.db_func import get_or_create_user, update_user, create_links, get_link_from_id, create_work_link_request, \
    get_work_request_from_id, create_cash_outs, get_cash_out_from_id, create_link
from services.func import get_all_time_cash, get_all_worked_link

logger, err_log = get_my_loggers()


class IsPrivate(BaseFilter):
    async def __call__(self, message: Message | CallbackQuery) -> bool:
        if isinstance(message, CallbackQuery):
            message = message.message
        # print(f'Проверка на частность: {message.chat.type}\n')
        return message.chat.type == 'private'


router: Router = Router()
router.message.filter()


class FSMWebUserMenu(StatesGroup):
    menu = State()
    change_view = State()


# -----Просмотр инфо по вэбмастерам-----
@router.callback_query(F.data == 'active_web')
async def send_link(callback: CallbackQuery, state: FSMContext, bot: Bot):
    # await callback.message.delete()
    logger.debug('active_web')
    menu = WebUserMenu()
    text = menu.text()
    await state.set_state(FSMWebUserMenu.menu)
    await state.update_data(page=0)
    await callback.message.edit_text(text=text, reply_markup=menu.nav_menu())


@router.callback_query(F.data.in_(['<<', 'back', '>>']))
async def active_web_n(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    data = await state.get_data()
    print('data', data)
    page = data.get('page')
    if callback.data == '<<':
        page -= 1
    elif callback.data == '>>':
        page += 1
    await state.update_data(page=page)
    menu = WebUserMenu()
    await callback.message.edit_reply_markup(reply_markup=menu.nav_menu(page=page))


@router.callback_query(F.data.startswith('active_web_n:'))
async def active_web_n(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    user_id = int(callback.data.split('active_web_n:')[1])
    logger.debug('active_web')
    menu = WebUserMenu(user_id)
    text = menu.user_stat()
    await state.update_data(user_id=user_id)
    await callback.message.edit_text(text=text, reply_markup=menu.nav_menu(user_id))
# -----Конец блока просмотр инфо по вэбмастерам-----


# -----Просмотр роликов------
@router.callback_query(F.data == 'videos')
async def videos(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    await state.clear()
    await state.set_state(FSMWebUserMenu.menu)
    kb = {'за 7 дней': 'links_period:4', 'за 14 дней+': 'links_period:1', 'за месяц': 'links_period:2', 'За все время': 'links_period:3', 'Назад': 'cancel'}
    await callback.message.edit_text('Выберите период', reply_markup=custom_kb(1, kb))


@router.callback_query(F.data.startswith('links_period:'))
async def links_period(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    print(callback.data.split(':'))
    link_period = int(callback.data.split(':')[1])
    user_id = 0
    if len(callback.data.split(':')) == 3:
        user_id = int(callback.data.split(':')[2])
    link_menu = LinkMenu(link_period=link_period, user_id=user_id)
    text = link_menu.text()
    page = 0
    kb = link_menu.nav_menu(page=page)
    await state.update_data(link_period=link_period, user_id=user_id, page=0)
    await callback.message.edit_text(text=text, reply_markup=kb)


@router.callback_query(F.data.in_(['link<<', 'link_back', 'link>>']))
async def active_web_n(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    data = await state.get_data()
    link_period = data.get('link_period')
    page = data.get('page')
    if callback.data == 'link<<':
        page -= 1
    elif callback.data == 'link>>':
        page += 1
    await state.update_data(page=page)
    menu = LinkMenu(link_period=link_period)
    await callback.message.edit_reply_markup(reply_markup=menu.nav_menu(page=page))


# Корректировка ссылки
@router.callback_query(F.data.startswith('links_id:'))
async def links_period(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    data = await state.get_data()
    link_id = int(callback.data.split('links_id:')[1])
    link_period = data.get('link_period')
    link = get_link_from_id(link_id)
    print(data)
    link_menu = LinkMenu(n=link_id, **data)
    text = link_menu.link_stat(link_id)
    print(data)
    menu = link_menu.nav_menu()
    await callback.message.edit_text(text=text, reply_markup=menu)


@router.callback_query(F.data.startswith('link_view_change:'))
async def link_view_change(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    link_id = int(callback.data.split('link_view_change:')[1])
    link = get_link_from_id(link_id)
    if link.view_count:
        await callback.message.delete()
        await callback.message.answer('Просмотры уже назначены')
        return
    cpm = link.owner.cpm
    await state.update_data(link_id=link_id, cpm=cpm)
    await callback.message.answer(f'Текущий CPM: {cpm}\nВведите количество просмотров')
    await state.set_state(FSMWebUserMenu.change_view)


@router.message(StateFilter(FSMWebUserMenu.change_view))
async def change_view(message: Message, state: FSMContext, bot: Bot):
    logger.debug(change_view)
    try:
        view_count = int(message.text.strip())
        data = await state.get_data()
        cpm = data.get('cpm')
        link_id = data.get('link_id')
        cost = int(view_count / 1000 * cpm)
        link = get_link_from_id(link_id)
        link.set('view_count', view_count)
        link.set('cost', cost)
        user = link.owner
        user.set('cash', user.cash + cost)
        await message.answer(f'Просмотры для ролика {link_id} установлены. Стоимость: {cost} рублей', reply_markup=admin_start_kb)
        await state.clear()

    except ValueError:
        await message.answer('Введите целое число')
    except Exception as err:
        logger.error(err)
        await message.answer(f'error: {str(err)}')
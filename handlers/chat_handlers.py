import datetime
import json

from aiogram import Router, Bot, F
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, StateFilter, BaseFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from config_data.bot_conf import get_my_loggers, conf
from database.db import User, LinkMenu, WebUserMenu
from keyboards.keyboards import start_kb, menu_kb, admin_start_kb, custom_kb, not_auth_start_kb
from lexicon.lexicon import LEXICON
from services.db_func import get_or_create_user, get_user_from_id, update_user, get_request_from_id, get_link_from_id, \
    get_work_request_from_id, create_work_link, get_cash_out_from_id, get_reg_from_id, create_cash_outs
from services.func import get_unconfirmed_reg

logger, err_log = get_my_loggers()


class IsAdmin(BaseFilter):
    def __init__(self) -> None:
        self.admins = conf.tg_bot.admin_ids

    async def __call__(self, message: Message) -> bool:
        return str(message.from_user.id) in self.admins


class IsFromGroup(BaseFilter):
    def __init__(self) -> None:
        self.moderator_chat_id = str(conf.tg_bot.GROUP_ID)

    async def __call__(self, message: Message | CallbackQuery) -> bool:
        if isinstance(message, CallbackQuery):
            message = message.message
        print(f'Проверка на группу\n'
              f'{message.chat.id} == {self.moderator_chat_id}: {bool(str(message.chat.id) == self.moderator_chat_id)}'
              )
        return str(message.chat.id) in self.moderator_chat_id

class IsAdminPrivate(BaseFilter):
    def __init__(self) -> None:
        self.GROUP_ID = int(conf.tg_bot.GROUP_ID)

    async def __call__(self, message: Message, event_from_user, bot: Bot, *args, **kwargs) -> bool:
        if isinstance(message, CallbackQuery):
            message = message.message
        member = await bot.get_chat_member(chat_id=self.GROUP_ID, user_id=event_from_user.id)
        status = member.status
        print(status)
        is_moderator = status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
        return is_moderator and message.chat.type == 'private'


router = Router()
router.message.filter(or_f(IsFromGroup(), IsAdminPrivate()))
router.callback_query.filter(or_f(IsFromGroup(), IsAdminPrivate()))


class FSMAdmin(StatesGroup):
    a = State()
    reject = State()


class FSMLink(StatesGroup):
    confirm = State()
    reject = State()


# @router.message(Command(commands=["start"]))
# async def process_start_command(message: Message, state: FSMContext):
#     await state.clear()
#     await message.answer('Состояние сброшено')

@router.callback_query(F.data == 'cancel')
async def operation_in(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug('chat cancel-start')
    await callback.message.delete()
    # await callback.message.answer('Режим модератора', reply_markup=ReplyKeyboardRemove())
    await callback.message.answer('Главное меню модератора', reply_markup=admin_start_kb)


@router.message(Command(commands=["start"]))
async def process_start_command(message: Message, state: FSMContext, bot: Bot):
    logger.debug('chat start')
    print(message.chat.id)
    # await message.answer('Режим модератора', reply_markup=ReplyKeyboardRemove())
    # await message.delete_reply_markup(None)
    await message.answer('Главное меню модератора', reply_markup=admin_start_kb)


class FSMAdminReg(StatesGroup):
    confirm = State()
    reject = State()


# Завяки на регистрацию (РЕГЗАЯВКА) ****************************
@router.callback_query(F.data == 'reg_list')
async def reg_list(callback: CallbackQuery, state: FSMContext, bot: Bot):
    uncofirmed_reg = get_unconfirmed_reg()
    btn = {}
    text = 'Заявки:\n'
    for reg in uncofirmed_reg:
        text += f'{reg.id}. {reg.text}\n'
        btn[f'Принять {reg.id} {reg.owner.username}'] = f'confirm_reg:{reg.id}'
        btn[f'Отклонить {reg.id} {reg.owner.username}'] = f'reject_reg:{reg.id}'
    btn['Отмена'] = 'cancel'
    await callback.message.edit_text(text=text, reply_markup=custom_kb(2, btn))


@router.callback_query(F.data.startswith('reject_reg:'))
async def reject_reg(callback: CallbackQuery, state: FSMContext, bot: Bot):
    print(callback.data)
    await callback.message.delete()
    await state.set_state(FSMAdminReg.reject)
    request_id = int(callback.data.split('reject_reg:')[-1])
    await state.update_data(request_id=request_id)
    await callback.message.answer('Укажите причину:')


@router.message(StateFilter(FSMAdminReg.reject))
async def operation_cost(message: Message, state: FSMContext, bot: Bot):
    reject_text = message.text.strip()
    data = await state.get_data()
    request_id = data['request_id']
    request = get_request_from_id(request_id)
    client = get_user_from_id(request.user_id)
    request.set('status', -1)
    request.set('reject_text', reject_text)
    reg = get_reg_from_id(request_id)
    msg = Message(**json.loads(reg.msg))
    msg = Message.model_validate(msg).as_(bot)
    await state.clear()
    await bot.send_message(chat_id=client.tg_id, text=f'Ваша заяка отклонена:\n{reject_text}')
    await message.answer(text=f'Заявка отклонена\n{reg.text}')
    await state.clear()
    await msg.edit_text(text=msg.text + f'<b>\n\nОтклонено {message.from_user.username or message.from_user.id}\n{reject_text}</b>')


@router.callback_query(F.data.startswith('confirm_reg:'))
async def in_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    request_id = int(callback.data.split('confirm_reg:')[-1])
    request = get_request_from_id(request_id)
    user = request.owner
    update_user(user, {'is_active': 1})
    request.set('status', 1)
    await bot.send_message(chat_id=user.tg_id, text='Ваша заяка одобрена')
    msg = Message(**json.loads(request.msg))
    msg = Message.model_validate(msg).as_(bot)
    btn = {}
    text = 'Заявки:\n'
    uncofirmed_reg = get_unconfirmed_reg()
    for reg in uncofirmed_reg:
        text += f'{reg.id}. {reg.text}\n'
        btn[f'Принять {reg.id} {reg.owner.username}'] = f'confirm_reg:{reg.id}'
        btn[f'Отклонить {reg.id} {reg.owner.username}'] = f'reject_reg:{reg.id}'
    btn['Отмена'] = 'cancel'
    await callback.message.answer(text=text, reply_markup=custom_kb(2, btn))
    await state.clear()
    await msg.edit_text(text=msg.text + f'<b>\n\nОдобрено</b> {callback.from_user.username or callback.from_user.id}')


# ----------------Подтверждение заявки из группы-----------------
class FSMConfirmRequest(StatesGroup):
    select_cpm = State()
    write_channel = State()


@router.callback_query(F.data.startswith('confirm_user_'))
async def in_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    request_id = int(callback.data.split('confirm_user_')[-1])
    await callback.message.answer('Укажите CPM')
    await state.set_state(FSMConfirmRequest.select_cpm)
    await state.update_data(request_id=request_id, message=callback.message, callback=callback)


@router.message(StateFilter(FSMConfirmRequest.select_cpm))
async def select_cpm(message: Message, state: FSMContext, bot: Bot):
    try:
        cpm = message.text.strip()
        cpm = float(cpm)
        await state.update_data(cpm=cpm)
        await message.answer('Укажите список каналов')
        await state.set_state(FSMConfirmRequest.write_channel)
    except ValueError:
        await message.answer('Введите корректное число')


@router.message(StateFilter(FSMConfirmRequest.write_channel))
async def write_channel(message: Message, state: FSMContext, bot: Bot):
    channels = message.text.strip()
    await state.update_data(channels=channels)
    data = await state.get_data()
    request_id = data.get('request_id')
    request = get_request_from_id(request_id)
    user = get_user_from_id(request.user_id)
    data = await state.get_data()
    cpm = data.get('cpm')
    update_user(user, {'is_active': 1, 'cpm': cpm})
    request.set('status', 1)
    await bot.send_message(chat_id=user.tg_id, text=f'Мы готовы предложить Вам сотрудничество по ставке {cpm} рублей за тысячу просмотров с каналами:\n{channels}\n\nТеперь, когда вы будете выкладывать видео, вы должны их скинуть в этот чат и указать дату на момент выкладки ролика в формате (01.01.2024)')
    await bot.send_message(chat_id=user.tg_id,
                           text='https://drive.google.com/drive/folders/1NWUx7VkKpa9ySTeNkojyho-vnj8RjEdj?usp=sharing',
                           reply_markup=start_kb)
    message: Message = data.get('message')
    callback: CallbackQuery = data.get('callback')
    await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=message.message_id, reply_markup=None)
    await bot.edit_message_text(text=message.text + f'<b>\n\nОдобрено</b> {callback.from_user.username or callback.from_user.id}',
                                chat_id=callback.message.chat.id,
                                message_id=message.message_id)
    await state.clear()


@router.callback_query(F.data.startswith('reject_user_'))
async def reject(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.set_state(FSMAdmin.reject)
    request_id = int(callback.data.split('reject_user_')[-1])
    await state.update_data(request_id=request_id, msg=callback.message)
    await callback.message.edit_reply_markup(None)
    # await callback.message.answer('Укажите причину:')

    data = await state.get_data()
    msg = data['msg']
    request_id = data['request_id']
    request = get_request_from_id(request_id)
    client = get_user_from_id(request.user_id)
    request.set('status', -1)
    reject_text = ''
    request.set('reject_text', reject_text)
    await bot.send_message(chat_id=client.tg_id, text=f'К сожалению мы не готовы предложить вам сотрудничество')
    await msg.edit_text(text=msg.text + f'<b>\n\nОтклонено {callback.message.from_user.username or callback.message.from_user.id}\n{reject_text}</b>')
    await state.clear()
# ----------------Конец Подтверждение заявки-----------------


# Заявки на вывод средств **********************
class FSMCashOut(StatesGroup):
    reject = State()


@router.callback_query(F.data.startswith('cash_out_confirm:'))
async def cash_conf(callback: CallbackQuery, state: FSMContext, bot: Bot):
    cash_out_id = int(callback.data.split('cash_out_confirm:')[-1])
    cash_out = get_cash_out_from_id(cash_out_id)
    cash_out.set('status', 1)
    moderator = get_or_create_user(callback.from_user)
    cash_out.set('moderator_id', moderator.id)
    await callback.message.answer(f'Выплата по заявке № {cash_out_id} подтверждена')
    # Отправка клиенту
    client = get_user_from_id(cash_out.user_id)
    # new_cash = client.cash - cash_out.cost
    text = f'Ваша заявка № {cash_out_id} на сумму {cash_out.cost} подтверждена\n'
    text += f'сумма {cash_out.cost} рублей будет переведена на ваш кошелек {cash_out.trc20} по курсу местного банка в течении 5 рабочих дней'
    await bot.send_message(chat_id=client.tg_id,
                           text=text)
    # client.set('cash', new_cash)
    # Меняем сообщение в группе
    await bot.edit_message_text(text=callback.message.text + f'\nПодтверждено {callback.from_user.username}',
                                chat_id=conf.tg_bot.GROUP_ID, message_id=callback.message.message_id)


@router.callback_query(F.data.startswith('cash_out_reject:'))
async def cash_conf(callback: CallbackQuery, state: FSMContext, bot: Bot):
    cash_out_id = int(callback.data.split('cash_out_reject:')[-1])
    await callback.message.answer(f'Укажите причину отмены заявки № {cash_out_id}')
    await state.set_state(FSMCashOut.reject)
    await state.update_data(cash_out_id=cash_out_id, msg=callback.message)


@router.message(StateFilter(FSMCashOut.reject))
async def cash_rej_verdict(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    msg = data['msg']
    verdict = message.text.strip()
    await state.update_data(verdict=verdict)
    cash_out_id = data['cash_out_id']
    cash_out = get_cash_out_from_id(cash_out_id)
    cash_out.set('status', -1)
    moderator = get_or_create_user(message.from_user)
    cash_out.set('moderator_id', moderator.id)
    cash_out.set('reject_text', verdict)
    await message.answer(f'Выплата по заявке № {cash_out_id} отклонена')
    # Отправка клиенту
    client = get_user_from_id(cash_out.user_id)
    await bot.send_message(chat_id=client.tg_id,
                           text=f'Ваша заявка № {cash_out_id} на сумму {cash_out.cost} ОТКЛОНЕНА:\n{verdict}')
    # Меняем сообщение в группе
    await bot.edit_message_text(text=msg.text + f'\nОТКЛОНЕНО {message.from_user.username}',
                                chat_id=conf.tg_bot.GROUP_ID, message_id=msg.message_id)
# КОНЕЦ Заявки на вывод средств **********************


# -----------------Webuser--------------------


class FSMWebUserMenu(StatesGroup):
    menu = State()
    change_view = State()
    change_cpm = State()
    deactivate = State()

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
    await callback.message.delete()
    link_id = int(callback.data.split('link_view_change:')[1])
    link = get_link_from_id(link_id)
    if link.view_count:
        await callback.message.delete()
        await callback.message.answer('Просмотры уже назначены')
        return
    cpm = link.owner.cpm
    await state.update_data(link_id=link_id, cpm=cpm)
    await callback.message.answer(f'Текущий CPM: {cpm}\nВведите количество просмотров для ролика {link.id} пользователя {link.owner.username}')
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


# Смена CPM
@router.callback_query(F.data.startswith('change_cpm:'))
async def change_cpm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    user_id = int(callback.data.split('change_cpm:')[1])
    user = get_user_from_id(user_id)
    await state.update_data(user_id=user_id)
    await callback.message.delete()
    await callback.message.answer(f'Укажите новый CPM для пользователя {user.username}')
    await state.set_state(FSMWebUserMenu.change_cpm)


@router.message(StateFilter(FSMWebUserMenu.change_cpm))
async def change_cpm(message: Message, state: FSMContext, bot: Bot):
    logger.debug(change_view)
    try:
        new_cpm = float(message.text.strip())
        data = await state.get_data()
        user_id = data.get('user_id')
        user = get_user_from_id(user_id)
        user.set('cpm', new_cpm)
        await message.answer(f'Новый СРМ для пользователя {user.username} установлен на {new_cpm}', reply_markup=admin_start_kb)
        await state.clear()

    except ValueError:
        await message.answer('Введите число')
    except Exception as err:
        logger.error(err)
        await message.answer(f'error: {str(err)}')


# Отключение мастера
@router.callback_query(F.data.startswith('deactivate:'))
async def deactivate(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    user_id = int(callback.data.split('deactivate:')[1])
    user = get_user_from_id(user_id)
    await state.update_data(user_id=user_id)
    kb = {'Отключить без выплаты': 'deactivate_0', 'Отключить и рассчитать': 'deactivate_1'}
    await callback.message.answer(f'Деактивация пользователя {user.username}.\nВыберите режим', reply_markup=custom_kb(1, kb))


@router.callback_query(F.data.startswith('deactivate_'))
async def deactivate_(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug(callback.data)
    await callback.message.delete()
    mode = callback.data.split('deactivate_')[1]
    data = await state.get_data()
    user_id = data.get('user_id')
    user = get_user_from_id(user_id)
    trc20 = ''
    if mode == '1' and user.cash > 0:
        # Создаем запрос на вывод средств
        cash = user.cash
        trc20 = user.trc20
        user.set('cash', 0)
        cash_out_id = create_cash_outs(user.id, cash, trc20)
        btn = {'Подтвердить': f'cash_out_confirm:{cash_out_id}',
               'Отклонить': f'cash_out_reject:{cash_out_id}'}
        text = f'Заявка при ДЕАКТИВАЦИИ№ {cash_out_id} на вывод {cash} р. от @{user.username or user.tg_id} на кошелек {trc20}'
        msg = await bot.send_message(chat_id=conf.tg_bot.GROUP_ID, text=text, reply_markup=custom_kb(2, btn))
        await bot.send_message(chat_id=user.tg_id, text=f'Вас отключили от работы, ждите последней выплаты в сумме {cash} на кошелек {trc20}')
        await callback.message.answer(f'Пользователь {user.username} деактивирован с выплатой')
        cash_out = get_cash_out_from_id(cash_out_id)
        cash_out.set('msg', msg.model_dump_json())
    else:
        await bot.send_message(chat_id=user.tg_id,
                               text=f'Вас отключили от работы без последующих вознаграждений', reply_markup=not_auth_start_kb)
        await callback.message.answer(f'Пользователь {user.username} деактивирован без выплаты')

    user.set('is_active', 0)




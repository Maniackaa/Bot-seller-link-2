import datetime
import json

from aiogram import Router, Bot, F
from aiogram.filters import Command, StateFilter, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from config_data.bot_conf import get_my_loggers, conf
from database.db import User
from keyboards.keyboards import start_kb, menu_kb, admin_start_kb, custom_kb
from lexicon.lexicon import LEXICON
from services.db_func import get_or_create_user, get_user_from_id, update_user, get_request_from_id, get_link_from_id, \
    get_work_request_from_id, create_work_link, get_cash_out_from_id, get_reg_from_id
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


router = Router()
router.message.filter(IsFromGroup())
router.callback_query.filter(IsFromGroup())


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




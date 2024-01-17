import json
import time

from aiogram import Router, Bot, F
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, StateFilter, BaseFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from config_data.bot_conf import get_my_loggers, conf
from database.db import User
from handlers.chat_handlers import IsFromGroup
from keyboards.keyboards import start_kb, admin_start_kb, custom_kb
from lexicon.lexicon import LEXICON
from services.db_func import get_or_create_user, get_user_from_id, update_user, get_request_from_id, get_link_from_id, \
    get_reg_from_id, get_work_request_from_id, create_work_link
from services.func import get_users_with_uncofirmed_link, get_user_uncofirmed_link, get_unconfirmed_reg, \
    get_unconfirmed_work_req

logger, err_log = get_my_loggers()


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




# class IsAdminPrivate(BaseFilter):
#     async def __call__(self, message: Message, event_from_user, bot: Bot, *args, **kwargs) -> bool:
#         return False


router = Router()
router.message.filter(or_f(IsFromGroup(), IsAdminPrivate()))
router.callback_query.filter(or_f(IsFromGroup(), IsAdminPrivate()))


class FSMAdminLink(StatesGroup):
    confirm = State()
    reject = State()




@router.callback_query(F.data == 'cancel')
async def operation_in(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug('admin cancel  start')
    await callback.message.delete()
    # await callback.message.answer('Режим модератора', reply_markup=ReplyKeyboardRemove())
    await callback.message.answer('Главное меню модератора', reply_markup=admin_start_kb)


@router.message(Command(commands=["start"]))
async def process_start_command(message: Message, state: FSMContext):
    logger.debug('admin start')
    user = get_or_create_user(message.from_user)
    # await message.answer('Режим модератора', reply_markup=ReplyKeyboardRemove())
    await message.answer('Главное меню модератора', reply_markup=admin_start_kb)



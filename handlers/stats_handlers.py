from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from config_data.bot_conf import get_my_loggers
from database.db import Session, Link
from keyboards.keyboards import admin_start_kb
from services.db_func import get_links, get_stats

router = Router()

logger, err_log = get_my_loggers()


@router.callback_query(F.data == 'stats')
async def stats(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug('stats')
    all_link = get_links()
    text = 'Статистика за весь период:\n'
    text += get_stats(all_link)
    text += '\nСтатистика за месяц:\n'
    all_link = get_links(30)
    text += get_stats(all_link)
    text += '\nСтатистика за 2 недели:\n'
    all_link = get_links(14)
    text += get_stats(all_link)
    await callback.message.edit_text(text=text)

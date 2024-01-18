from aiogram import F, Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy import select
import pandas as pd

from config_data.bot_conf import get_my_loggers, BASE_DIR
from database.db import Session, Link
from keyboards.keyboards import admin_start_kb
from services.db_func import get_links, get_stats, save_stat_to_df

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
    await callback.message.edit_text(text=text, reply_markup=admin_start_kb)


@router.callback_query(F.data == 'export')
async def stats(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug('export')
    save_stat_to_df()
    file = FSInputFile(BASE_DIR / 'text.xlsx')
    await bot.send_document(chat_id=callback.message.chat.id, document=file)


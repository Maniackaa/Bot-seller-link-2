import asyncio

from aiogram import Dispatcher, types, Router, Bot, F
from aiogram.filters import Command, CommandStart, StateFilter, BaseFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, URLInputFile, ReplyKeyboardRemove

from aiogram.fsm.context import FSMContext

from config_data.bot_conf import get_my_loggers, conf
from database.db import User
from keyboards.keyboards import start_kb, contact_kb, admin_start_kb, custom_kb, menu_kb, not_auth_start_kb
from lexicon.lexicon import LEXICON
from services.db_func import get_or_create_user, update_user, create_request, get_request_from_id


logger, err_log = get_my_loggers()


class IsPrivate(BaseFilter):
    async def __call__(self, message: Message | CallbackQuery) -> bool:
        if isinstance(message, CallbackQuery):
            message = message.message
        # print(f'Проверка на частность: {message.chat.type}\n')
        return message.chat.type == 'private'


router: Router = Router()
router.message.filter(IsPrivate())
router.callback_query.filter(IsPrivate())


class FSMCheckUser(StatesGroup):
    q1 = 'Какой тип контента вы создаете (SHORTS, полноформатные видео)?'
    anwer1 = [
        '- короткие ролики с вашим баннером',
        '- интеграция в больших роликах',
        '- что - то другое']

    confirm = State()


class FSMAnket(StatesGroup):
    anket = State()
    text = State()
    confirm = State()
    # [('Вопрос', (Варианты,...), Свой вариант - True/False))]
    question_blocks = [
        (
            'Какой тип контента вы создаете (SHORTS, полноформатные видео)?',
            ('короткие ролики с вашим баннером',
             'интеграция в больших роликах',
             'Что-то другое'
             ),
            False
        ),
        (
            ' Какой у вас источник?',
            ('ютуб',
             'инстаграм',
             'тикток'
             ),
            False
        ),
        (
            'Сколько просмотров в у вас было за предыдущий месяц в сумме со всех каналов?',
            ('до миллиона',
             'от 1 до 5 миллионов',
             'от 6 до 10 миллионов',
             'от 10 до 20 миллионов',
             'от 30 до 50 миллионов',
             'от 50 до 100 миллионов',
             'больше 100 миллионов',
             ),
            False
        ),
        (
            'Укажите ваш канал. Если хотите подать несколько каналов, подавайте их списком',
            '',
            False
        ),

    ]
    answers = {}


def get_question_kb_button(question__num):
    kb = {}
    for num, answer in enumerate(FSMAnket.question_blocks[question__num][1]):
        kb[answer] = f'answer:{question__num}:{num}'
    reply_markup = custom_kb(1, kb)
    return reply_markup


@router.callback_query(F.data == 'cancel')
async def operation_in(callback: CallbackQuery, state: FSMContext, bot: Bot):
    logger.debug('new user cancel')
    await callback.message.delete()
    await state.clear()
    await callback.message.answer('Введите /start или Меню для начала работы', reply_markup=not_auth_start_kb)

@router.message(F.text == 'Меню')
@router.message(Command(commands=["start"]))
async def process_start_command(message: Message, state: FSMContext):
    logger.debug('new')
    try:
        await state.clear()
        tg_user = message.from_user
        user: User = get_or_create_user(tg_user)
        if not user.is_active:
            await state.set_state(FSMAnket.anket)
            await state.update_data(question_num=0)
            await message.answer('Ответьте на вопросы', reply_markup=not_auth_start_kb)
            await message.answer('Какой тип контента вы создаете (SHORTS, полноформатные видео)?',
                                 reply_markup=get_question_kb_button(0))
        else:
            await message.answer('Теперь, когда вы будете выкладывать видео, вы должны их скинуть в этот чат и указать дату на момент выкладки ролика в формате (01.01.2024)', reply_markup=start_kb)
    except Exception as err:
        logger.error(err)


def format_confirm_text(answers: dict) -> str:
    # {0: 'короткие ролики с вашим баннером', 1: 'от 30 до 50 миллионов',...}
    text = ''
    for num, question_block in enumerate(FSMAnket.question_blocks):
        question = question_block[0]
        answer = answers[num]
        text += f'<b>{question}:</b>\n{answer}\n\n'
    return text

# Анкетирование
@router.callback_query(F.data.startswith('answer'))
async def answer_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    print(callback.data)
    split_data = callback.data.split(':')
    question_num = int(split_data[1])
    answer_num = int(split_data[2])
    print(question_num, answer_num)
    question_blocks = FSMAnket.question_blocks
    # Сохраняем ответ
    answer = question_blocks[question_num][1][answer_num]
    print('Ответ:', answer)
    FSMAnket.answers[question_num] = answer

    if question_num + 1 < len(question_blocks):
        # Следующий вопрос:
        new_question_block = question_blocks[question_num + 1]
        new_question = new_question_block[0]
        new_answers = new_question_block[1]
        print(f'Следующий вопрос: {new_question}')
        print(f'Следующие ответы: {new_answers}')
        if new_answers:
            await callback.message.edit_text(text=new_question, reply_markup=get_question_kb_button(question_num + 1))
        else:
            print('Вопрос без вариантов ответа')
            await state.set_state(FSMAnket.text)
            await callback.message.delete()
            await callback.message.answer(new_question)
            await state.update_data(question_num=question_num + 1)
    else:
        # Вопросы кончились
        print('Вопросы кончились')
        await callback.message.delete()
        text = format_confirm_text(FSMAnket.answers)
        confirm_btn = {
            'Отменить': 'cancel',
            'Отправить': 'confirm'
        }
        await callback.message.answer(text, reply_markup=custom_kb(2, confirm_btn))
        await state.set_state(FSMAnket.confirm)
    print(f'Все ответы: {FSMAnket.answers}')


@router.message(StateFilter(FSMAnket.text))
async def questions_text(message: Message, state: FSMContext, bot: Bot):
    answer = message.text
    data = await state.get_data()
    question_num = data['question_num']
    # Сохраняем ответ
    FSMAnket.answers[question_num] = answer
    print(f'Все ответы: {FSMAnket.answers}')

    question_blocks = FSMAnket.question_blocks
    if question_num + 1 < len(question_blocks):
        # Следующий вопрос:
        new_question_block = question_blocks[question_num + 1]
        new_question = new_question_block[0]
        new_answers = new_question_block[1]
        print(f'Следующий вопрос: {new_question}')
        print(f'Следующие ответы: {new_answers}')
        if new_answers:
            await message.answer(text=new_question, reply_markup=get_question_kb_button(question_num + 1))
            await state.set_state(FSMAnket.anket)
        else:
            print('Вопрос без вариантов ответа')
            await state.set_state(FSMAnket.text)
            await message.answer(new_question)
        await state.update_data(question_num=question_num + 1)
    else:
        # Вопросы кончились
        print('Вопросы кончились')
        text = format_confirm_text(FSMAnket.answers)
        confirm_btn = {
            'Отменить': 'cancel',
            'Отправить': 'confirm'
        }
        await message.answer(text, reply_markup=custom_kb(2, confirm_btn))
        await state.set_state(FSMAnket.confirm)


def format_request(user, answers):

    msg = f'Новая заявка на подключение канала @{user.username or user.tg_id}):\n'
    msg += f'Источник: {answers[1]}\n'
    msg += f'Просмотры: {answers[2]}\n'
    # for answer in answers:
    #     msg += f'{answer}\n'
    return msg


@router.callback_query(StateFilter(FSMAnket.confirm), F.data == 'confirm')
async def in_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.message.delete_reply_markup()
        await callback.message.answer('Ваша завка отправлена. Ожидайте ответа.')

        user = get_or_create_user(callback.from_user)

        text = format_request(user, FSMAnket.answers)
        source = FSMAnket.answers[1]
        request_id = create_request(user, text, source)
        btn = {'Принять': f'confirm_user_{request_id}', 'Отклонить': f'reject_user_{request_id}'}
        request_msg = await bot.send_message(chat_id=conf.tg_bot.GROUP_ID, text=text, reply_markup=custom_kb(2, btn))
        request = get_request_from_id(request_id)
        request.set('msg', request_msg.model_dump_json())
        await state.clear()

        end_answer = """Спасибо. 
Пока мы изучаем вашу заявку, вступите пока в наш телеграм канал: https://t.me/+IxdcozjtVdI1OTNk
Там вы сможете ознакомиться с нашими условиями в закрепленном комментарии .
"""
        await callback.message.answer(end_answer)
    except Exception as err:
        logger.error(err)
        raise err

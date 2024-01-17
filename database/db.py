import asyncio
import datetime
from typing import Sequence

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic import json
from sqlalchemy import create_engine, ForeignKey, Date, String, DateTime, \
    Float, UniqueConstraint, Integer, LargeBinary, BLOB, select, ARRAY, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import sessionmaker
from sqlalchemy_utils.functions import database_exists, create_database

from config_data.bot_conf import conf, get_my_loggers, tz
from lexicon.lexicon import LEXICON

logger, err_log = get_my_loggers()

db_url = f"postgresql+psycopg2://{conf.db.db_user}:{conf.db.db_password}@{conf.db.db_host}:{conf.db.db_port}/{conf.db.database}"
engine = create_engine(db_url, echo=False)
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    def set(self, key, value):
        _session = Session(expire_on_commit=False)
        with _session:
            setattr(self, key, value)
            _session.add(self)
            _session.commit()
            logger.debug(f'Изменено значение {key} на {value}')
            return self


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement='auto')
    tg_id: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    register_date: Mapped[datetime.datetime] = mapped_column(DateTime(), nullable=True)
    fio: Mapped[str] = mapped_column(String(200), nullable=True)
    cash: Mapped[int] = mapped_column(Integer(), default=0)
    cpm: Mapped[float] = mapped_column(Float(precision=1), default=0)
    is_active: Mapped[int] = mapped_column(Integer(), default=0)
    trc20: Mapped[str] = mapped_column(String(50), nullable=True)
    links: Mapped[list['Link']] = relationship(back_populates='owner', lazy='subquery')
    requests: Mapped[list['Request']] = relationship(back_populates='owner', lazy='subquery')
    work_link: Mapped[int] = mapped_column(ForeignKey('work_links.id', ondelete='CASCADE'), nullable=True)
    work_link_requests: Mapped[list['WorkLinkRequest']] = relationship(back_populates='owner', lazy='subquery')
    cash_outs: Mapped[list['CashOut']] = relationship(back_populates='user', lazy='subquery')

    def __str__(self):
        return f'{self.id}. {self.username or "-"} ({self.fio}). Баланс {self.cash}'

    def __repr__(self):
        return f'{self.id}. {self.username or "-"} ({self.fio})'


class WebUserMenu:
    PAGINATE = 20

    def __init__(self, user_id=0):
        self.user_id = user_id

    @property
    def user(self):
        session = Session()
        with session:
            user = select(User).where(User.id == self.user_id)
            user = session.execute(user).scalar()
            return user

    @staticmethod
    def get_queryset():
        session = Session()
        with session:
            users = select(User).where(User.is_active == 1)
            users = session.execute(users).scalars().all()
            return users

    def text(self):
        if not self.user_id:
            text = f'Выберите вэбмастера'
        else:
            user = self.user
            text = f'Статистика пользователя {user.id}. {user.username}\n (CPM: {user.cpm})'
        return text

    @staticmethod
    def custom_kb(width: int, buttons_dict: dict, menus='') -> InlineKeyboardMarkup:
        kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
        buttons = []
        if menus:
            item_btn1 = InlineKeyboardButton(text='<<', callback_data='>>')
            stat_bn = InlineKeyboardButton(text=menus, callback_data='*')
            item_btn2 = InlineKeyboardButton(text='>>', callback_data='>>')
            kb_builder.row(item_btn1, stat_bn, item_btn2)
        for key, val in buttons_dict.items():
            callback_button = InlineKeyboardButton(
                text=key,
                callback_data=val)
            buttons.append(callback_button)
        kb_builder.row(*buttons, width=width)
        return kb_builder.as_markup()

    def nav_menu(self, user_id=0, page=0):
        if not user_id:
            queryset = self.get_queryset()
            max_page = len(queryset) // self.PAGINATE
            if len(queryset) % self.PAGINATE != 0:
                max_page += 1
            page = page % max_page
            start = self.PAGINATE * page
            end = start + self.PAGINATE
            logger.debug(f'page: {page}. {start} - {end}')
            users = queryset[start:end]
            nav_btn = {}
            for user in users:
                nav_btn[f'{user.id} {user.username}'] = f'active_web_n:{user.id}'
            if len(queryset) > self.PAGINATE:
                menus = f'{start + 1} - {min(end, len(queryset))} из {len(queryset)}'
            else:
                menus = ''
            return self.custom_kb(1, nav_btn, menus=menus)

        nav_btn = {}
        nav_btn.update({'Изменить CPM': f'change_cpm:{self.user_id}',
                        'Деактивировать пользователя': f'deactivate:{self.user_id}',
                        'за 7 дней': 'links_period:4',
                        'за 14 дней+': f'links_period:1:{user_id}',
                        'за месяц': f'links_period:2:{user_id}',
                        'За все время': f'links_period:3:{user_id}'})
        nav_btn.update({'Назад': 'back'})
        return self.custom_kb(1, nav_btn, menus='')

    def user_stat(self):
        if not self.user_id:
            return 'Выберети пользователя'
        text = f'Статистика пользователя {self.user.username} (CPM: {self.user.cpm})\n'
        link_types = ['youtube', 'instagram', 'tiktok']
        links: Sequence[Link] = self.user.links
        for link_type in link_types:
            text += f'{link_type}:\n'
            for link in links:
                if link.link_type == link_type:
                    data = [link.link, str(link.register_date.strftime('%d.%m.%Y')), str(link.view_count), str(link.cost)]
                    print(data)
                    text += ' - '.join(data)
                    text += '\n'
        return text[:4000]



class Request(Base):
    __tablename__ = 'requests'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement='auto')
    register_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True,
                                                default=lambda: datetime.datetime.now(tz=tz))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    owner: Mapped['User'] = relationship(back_populates='requests', lazy='subquery')
    text: Mapped[str] = mapped_column(String(4000), nullable=True)
    status: Mapped[int] = mapped_column(Integer(), default=0)
    reject_text: Mapped[str] = mapped_column(String(4000), nullable=True)
    msg: Mapped[json] = mapped_column(JSONB(), nullable=True)


class Link(Base):
    __tablename__ = 'links'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement='auto')
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    owner: Mapped['User'] = relationship(back_populates='links', lazy='subquery')
    register_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True,
                                                    default=lambda: datetime.datetime.now(tz=tz))
    link: Mapped[str] = mapped_column(String(1000), unique=True)
    link_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='created')
    moderator_id: Mapped[int] = mapped_column(Integer(), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer(), default=0)
    cost: Mapped[int] = mapped_column(Integer(), default=0)
    msg: Mapped[json] = mapped_column(JSONB(), nullable=True)

    def __str__(self):
        return f'{self.id}. {self.link}'

    def __repr__(self):
        return f'{self.id}. {self.link}'


class LinkMenu:
    PAGINATE = 2

    def __init__(self, n=None, user_id=0, link_period=3, **kwargs):
        self.n = n
        self.link_period = link_period
        self.user_id = user_id
        print(f'LinkMenu init: {self.n} period: {self.link_period} user {self.user_id}')

    @property
    def user(self):
        session = Session()
        with session:
            user = select(User).where(User.id == self.user_id)
            user = session.execute(user).scalar()
            return user

    @property
    def start_period(self):
        """
        за 7 дней: 4
        за 14 дней+: 1
        за месяц: 2
        За все время:3
        """
        if self.link_period == 3:
            return datetime.datetime(2023, 1, 1)
        elif self.link_period == 4:
            return datetime.datetime.now() - datetime.timedelta(days=7)
        elif self.link_period == 1:
            return datetime.datetime(2023, 1, 1)
        elif self.link_period == 2:
            return datetime.datetime.now() - datetime.timedelta(days=30)

    def get_queryset(self, start_date=datetime.datetime(2024, 1, 1)):
        session = Session()
        print(start_date)
        with session:
            links = select(Link).where(
                Link.cost == 0,
                Link.register_date > start_date
            )
            if self.link_period == 1:
                links = links.where(Link.register_date < datetime.datetime.now() - datetime.timedelta(days=14))
            if self.user_id:
                links = links.where(Link.owner_id == self.user_id)
            links = session.execute(links).scalars().all()
            return links

    def text(self):
        text = 'Просмотр роликов '
        print('text', f'user: {self.user_id}')
        if self.user_id:
            text += f'пользователя {self.user.username}\n'
        if self.link_period == 1:
            text += f'за 14+ дней\n'
        if self.link_period == 2:
            text += f'за месяц\n'
        if self.link_period == 3:
            text += f'за все время\n'
        print(f'start_period: {self.start_period}')
        links = self.get_queryset(start_date=self.start_period)
        print('links', links)
        link_types = ['youtube', 'instagram', 'tiktok']
        for link_type in link_types:
            text += f'\n<b>{link_type}:</b>\n'
            for link in links:
                if link.link_type == link_type:
                    data = [f'<a href="{link.link}">{link.id}. {link_type}</a>', str(link.register_date.strftime('%d.%m.%Y')), str(link.view_count), str(link.cost)]
                    text += ' - '.join(data)
                    text += '\n'
        text += '\n\nВыберите ролик'
        return text

    @staticmethod
    def custom_kb(width: int, buttons_dict: dict, menus='') -> InlineKeyboardMarkup:
        kb_builder: InlineKeyboardBuilder = InlineKeyboardBuilder()
        buttons = []
        if menus:
            item_btn1 = InlineKeyboardButton(text='<<', callback_data='link<<')
            stat_bn = InlineKeyboardButton(text=menus, callback_data='*')
            item_btn2 = InlineKeyboardButton(text='>>', callback_data='link>>')
            kb_builder.row(item_btn1, stat_bn, item_btn2)
        for key, val in buttons_dict.items():
            callback_button = InlineKeyboardButton(
                text=key,
                callback_data=val)
            buttons.append(callback_button)
        kb_builder.row(*buttons, width=width)
        return kb_builder.as_markup()

    def nav_menu(self, link_id=0, page=0):
        logger.debug(f'Меню LinkMenu. period: {self.link_period}, link_id: {link_id}, user: {self.user_id}')
        nav_btn = {}
        if self.n and self.get_link_from_id(self.n).view_count == 0:
            nav_btn.update({'Изменить количество просмотров': f'link_view_change:{self.n}'})
        if not link_id:
            queryset = self.get_queryset(start_date=self.start_period)
            menus = ''
            if queryset:
                max_page = len(queryset) // self.PAGINATE
                if len(queryset) % self.PAGINATE != 0:
                    max_page += 1
                page = page % max_page
                start = self.PAGINATE * page
                end = start + self.PAGINATE
                logger.debug(f'page: {page}. {start} - {end}')
                links: Sequence[Link] = queryset[start:end]
                for link in links:
                    nav_btn[f'{link.id}. {link.link_type} {link.register_date.strftime("%d.%m%Y")} ({link.view_count})'] = f'links_id:{link.id}'
                if len(queryset) > self.PAGINATE:
                    menus = f'{start + 1} - {min(end, len(queryset))} из {len(queryset)}'
            if self.user_id:
                nav_btn.update({'Назад': f'active_web_n:{self.user_id}'})
            else:
                nav_btn.update({'Назад': f'videos'})
            return self.custom_kb(1, nav_btn, menus=menus)
        nav_btn = {
            'Назад': 'link_back'
        }
        return self.custom_kb(1, nav_btn, menus='')

    @staticmethod
    def get_link_from_id(pk) -> Link:
        try:
            session = Session()
            with session:
                q = select(Link).filter(Link.id == pk)
                link = session.execute(q).scalars().one_or_none()
                return link
        except Exception as err:
            logger.error(err)

    def link_stat(self, pk):
        link: Link = self.get_link_from_id(pk)
        text = (
            f'Видео {link.id}. {link.link}\n'
            f'Пользователь: {link.owner.username}\n'
            f'Дата: {link.register_date.strftime("%d.%m.%Y")}\n'
            f'Просмотров: {link.view_count}\n'
            f'Стоимость: {link.cost}\n'
        )
        return text


class WorkLink(Base):
    __tablename__ = 'work_links'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement='auto')
    register_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True,
                                                    default=lambda: datetime.datetime.now(tz=tz))
    link: Mapped[str] = mapped_column(String(1000))
    worker_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    moderator_id: Mapped[int] = mapped_column(Integer(), nullable=True)

    def __str__(self):
        return f'{self.id}. {self.link}'

    def __repr__(self):
        return f'{self.id}. {self.link}'


class WorkLinkRequest(Base):
    __tablename__ = 'work_link_requests'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement='auto')
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    owner: Mapped['User'] = relationship(back_populates='work_link_requests', lazy='subquery')
    register_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True,
                                                    default=lambda: datetime.datetime.now(tz=tz))

    status: Mapped[int] = mapped_column(Integer(), default=0)
    reject_text: Mapped[str] = mapped_column(String(4000), nullable=True)
    msg: Mapped[json] = mapped_column(JSONB(), nullable=True)

    def __str__(self):
        return f'{self.id}. {self.owner_id}'

    def __repr__(self):
        return f'{self.id}. {self.owner_id}'


class CashOut(Base):
    __tablename__ = 'cash_outs'
    id: Mapped[int] = mapped_column(primary_key=True,
                                    autoincrement='auto')
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    user: Mapped['User'] = relationship(back_populates='cash_outs', lazy='subquery')
    trc20: Mapped[str] = mapped_column(String(50), nullable=True)
    cost: Mapped[int] = mapped_column(Integer(), default=0)
    status: Mapped[int] = mapped_column(Integer(), default=0)
    moderator_id: Mapped[int] = mapped_column(Integer(), nullable=True)
    msg: Mapped[json] = mapped_column(JSONB(), nullable=True)
    reject_text: Mapped[str] = mapped_column(String(1000), nullable=True)


if not database_exists(db_url):
    create_database(db_url)
Base.metadata.create_all(engine)

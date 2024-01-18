import asyncio
import datetime

import pandas as pd
from sqlalchemy import select, delete, distinct, Row, RowMapping
from sqlalchemy.exc import IntegrityError
from typing_extensions import Sequence

from config_data.bot_conf import get_my_loggers, BASE_DIR
from database.db import Session, User, Request, Link, WorkLinkRequest, WorkLink, CashOut

logger, err_log = get_my_loggers()


def check_user(id):
    """Возвращает найденных пользователей по tg_id"""
    # logger.debug(f'Ищем юзера {id}')
    with Session() as session:
        user: User = session.query(User).filter(User.tg_id == str(id)).one_or_none()
        # logger.debug(f'Результат: {user}')
        return user


# def get_user_from_id(pk) -> User:
#     """Возвращает найденного пользователя по id"""
#     # logger.debug(f'Ищем юзера {id}')
#     with Session() as session:
#         user: User = session.query(User).filter(User.id == pk).one_or_none()
#         # logger.debug(f'Результат: {user}')
#         return user


def get_user_from_id(pk) -> User:
    session = Session(expire_on_commit=False)
    with session:
        q = select(User).filter(User.id == pk)
        user = session.execute(q).scalars().one_or_none()
        return user


def get_or_create_user(user) -> User:
    """Из юзера ТГ возвращает сущестующего User ли создает его"""
    try:
        tg_id = user.id
        username = user.username
        logger.debug(f'username {username}')
        old_user = check_user(tg_id)
        if old_user:
            logger.debug('Пользователь есть в базе')
            return old_user
        logger.debug('Добавляем пользователя')
        with Session() as session:
            new_user = User(tg_id=tg_id,
                            username=username,
                            register_date=datetime.datetime.now()
                            )
            session.add(new_user)
            session.commit()
            logger.debug(f'Пользователь создан: {new_user}')
        return new_user
    except Exception as err:
        err_log.error('Пользователь не создан', exc_info=True)


def update_user(user: User, data: dict):
    try:
        logger.debug(f'Обновляем {user}: {data}')
        session = Session()
        with session:
            user: User = session.query(User).filter(User.id == user.id).first()
            for key, val in data.items():
                setattr(user, key, val)
            session.commit()
            logger.debug(f'Юзер обновлен {user}')
    except Exception as err:
        err_log.error(f'Ошибка обновления юзера {user}: {err}')


def create_request(user: User, text, source):
    logger.debug(f'Сохраняем запрос')
    session = Session()
    with session:
        request = Request(
            user_id=user.id,
            text=text,
            source=source
        )
        session.add(request)
        session.commit()
        logger.debug('Запрос сохранен')
        return request.id


def get_request_from_id(pk) -> Request:
    with Session() as session:
        req: Request = session.query(Request).filter(Request.id == pk).one_or_none()
        return req


def create_links(user: User, links: list):
    session = Session()
    with session:
        link_ids = []
        for link in links:
            link = Link(owner_id=user.id,
                        link=link)
            session.add(link)
            session.commit()
            link_ids.append(link.id)
        logger.debug('Запрос сохранен')
        return link_ids


def create_link(user: User, link, link_type):
    session = Session()
    try:
        with session:
            link = Link(owner_id=user.id,
                        link=link,
                        link_type=link_type
                        )
            session.add(link)
            session.commit()
            logger.debug('Запрос сохранен')
            return link.id
    except IntegrityError as err:
        logger.error(err)


def create_work_link_request(user: User):
    session = Session()
    with session:
        work = WorkLinkRequest(owner_id=user.id)
        session.add(work)
        session.commit()
        logger.debug('Запрос сохранен')
        return work.id


def create_work_link(user_id, link, moderator_id):
    session = Session()
    with session:
        work = WorkLink(worker_id=user_id,
                        link=link,
                        moderator_id=moderator_id)
        session.add(work)
        session.commit()
        logger.debug('Запрос сохранен')
        return work.id


def get_link_from_id(pk) -> Link:
    try:
        session = Session()
        with session:
            q = select(Link).filter(Link.id == pk)
            link = session.execute(q).scalars().one_or_none()
            return link
    except Exception as err:
        logger.error(err)

def get_reg_from_id(pk) -> Request:
    session = Session()
    with session:
        q = select(Request).filter(Request.id == pk)
        reg = session.execute(q).scalars().one_or_none()
        return reg


def get_work_request_from_id(pk) -> WorkLinkRequest:
    session = Session()
    with session:
        q = select(WorkLinkRequest).filter(WorkLinkRequest.id == pk)
        reg = session.execute(q).scalars().one_or_none()
        return reg


def create_cash_outs(user_id, cost, trc20) -> int:
    session = Session()
    with session:
        cash_out = CashOut(user_id=user_id, cost=cost, trc20=trc20)
        session.add(cash_out)
        session.commit()
        logger.debug('Запрос на вывод сохранен')
        return cash_out.id


def get_cash_out_from_id(pk) -> CashOut:
    session = Session()
    with session:
        q = select(CashOut).filter(CashOut.id == pk)
        cash_out = session.execute(q).scalars().one_or_none()
        return cash_out


def get_stats(queryset):
    link_types = ['youtube', 'instagram', 'tiktok']
    text = ''

    for link_type in link_types:
        link_count = 0
        view_count = 0
        cost = 0
        text += f'{link_type}\n'
        for link in queryset:
            if link.link_type == link_type:
                link_count += 1
                view_count += link.view_count
                cost += link.cost

        text += f'Ссылок: {link_count}.'
        text += f' Просмотров: {view_count}.'
        text += f' Выплат: {cost}.\n'

    link_count = 0
    view_count = 0
    cost = 0
    for link in queryset:
        link_count += 1
        view_count += link.view_count
        cost += link.cost
    text += f'Итого Ссылок: {link_count} Просмотров: {view_count} Выплат: {cost}\n'
    return text


def get_links(period=None) -> Sequence[Link]:
    session = Session(expire_on_commit=False)
    with session:
        all_link_q = select(Link)
        if period:
            all_link_q = all_link_q.where(Link.register_date > datetime.datetime.now() - datetime.timedelta(days=period))
        all_link: Sequence[Link] = session.execute(all_link_q).scalars().all()
        return all_link


def save_stat_to_df():
    """
    Сохраняет статистике в файл excel
    """
    path = BASE_DIR / 'text.xlsx'
    session = Session(expire_on_commit=False)
    with session:
        all_users = select(distinct(Link.owner_id))
        all_users: Sequence[Link] = session.execute(all_users).scalars().all()
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            pd.DataFrame().to_excel(writer, sheet_name='Info', startrow=0, startcol=0)

        for user_id in all_users:
            q = select(Link).where(Link.owner_id == user_id).order_by(Link.link_type.asc(), Link.register_date.asc())
            user_links: list[Link] = session.execute(q).scalars().all()
            print(user_links)
            user = get_user_from_id(user_id)
            columns = ['id', 'Дата', 'Cссылка', 'Источник', 'Просмотры', 'Выплата']
            rows = []
            for link in user_links:
                row = [link.id,
                       link.register_date.strftime('%d.%m.%Y'),
                       link.link,
                       link.link_type,
                       link.view_count,
                       link.cost]
                rows.append(row)
            df_to_save = pd.DataFrame(data=rows, index=None, columns=columns)
            with pd.ExcelWriter(path, engine="openpyxl", mode="a") as writer:
                df_to_save.to_excel(writer, sheet_name=str(f'{user.username} ({user.cpm})'), index=False, startrow=0, startcol=0)


if __name__ == '__main__':
    pass
    # client = get_user_from_id(1)
    # # print(client)
    # new_cash = client.cash + 100
    # client = client.set('cash', new_cash)
    # print(client)
    # r = get_request_from_id(1)
    # print(r)
    # r.set('reject_text', 'text')
    # asyncio.run(update_operation_in(['оступле333ние 1']))
    save_stat_to_df()





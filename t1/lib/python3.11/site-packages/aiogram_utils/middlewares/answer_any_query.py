from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware


class AnswerAnyQuery(BaseMiddleware):

    @staticmethod
    async def on_post_process_callback_query(query: types.CallbackQuery, *_):
        await query.answer()

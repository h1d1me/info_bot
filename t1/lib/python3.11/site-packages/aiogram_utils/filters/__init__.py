from aiogram import Dispatcher

from .buttons import CallbackQueryButton, InlineQueryButton, MessageButton
from .storage import StorageDataFilter


def setup(dp: Dispatcher):
    dp.filters_factory.bind(MessageButton, event_handlers=[
        dp.message_handlers,
        dp.edited_message_handlers,
    ])
    dp.filters_factory.bind(CallbackQueryButton, event_handlers=[
        dp.callback_query_handlers,
    ])
    dp.filters_factory.bind(InlineQueryButton, event_handlers=[
        dp.inline_query_handlers,
    ])
    dp.filters_factory.bind(StorageDataFilter, exclude_event_handlers=[
        dp.errors_handlers,
        dp.poll_handlers,
        dp.poll_answer_handlers,
    ])

from __future__ import annotations

import re
from abc import abstractmethod
from contextlib import suppress
from typing import Optional, Union

from aiogram import types
from aiogram.dispatcher.filters import BoundFilter
from aiogram.types import InlineKeyboardButton, KeyboardButton


class AbstractButtonFilter(BoundFilter):
    key = 'button'

    @abstractmethod
    def cast_button(self, button):
        """Cast button to string for matching"""

    @abstractmethod
    def cast_update(self, update_obj):
        """Cast update-obj to string for matching"""

    @staticmethod
    def make_regexp(text: str):
        return re.sub(r'{(.+?)}', r'(?P<\1>.+)', text)

    def __init__(self, button):
        self.buttons_regexps = []

        if not isinstance(button, (list, tuple, set)):
            button = [button]

        for item in button:
            if isinstance(item, str):
                button_data = item
            else:
                button_data = self.cast_button(item)

            if not isinstance(button_data, str):
                raise ValueError(f'Invalid data for {self.__class__.__name__} filter')

            self.buttons_regexps.append(self.make_regexp(button_data))

    def check_one(self, update_obj, button_regexp: str) -> Optional[dict]:
        with suppress(TypeError):
            match = re.fullmatch(button_regexp, self.cast_update(update_obj))

            if match:
                return {'button': match.groupdict()}

        if button_regexp == self.cast_update(update_obj):
            return {'button': {}}

    async def check(self, update_obj) -> Union[dict, bool]:
        for regexp in self.buttons_regexps:
            result = self.check_one(update_obj, regexp)
            if result:
                return result
        return False


class CallbackQueryButton(AbstractButtonFilter):

    def cast_button(self, button: InlineKeyboardButton):
        return button.callback_data

    def cast_update(self, update_obj: types.CallbackQuery):
        return update_obj.data


class InlineQueryButton(AbstractButtonFilter):

    def cast_button(self, button: InlineKeyboardButton):
        if button.switch_inline_query is None:
            return button.switch_inline_query_current_chat
        return button.switch_inline_query

    def cast_update(self, update_obj: types.InlineQuery):
        return update_obj.query


class MessageButton(AbstractButtonFilter):

    def cast_button(self, button: Union[KeyboardButton, InlineKeyboardButton]):
        if isinstance(button, KeyboardButton):
            return button.text

        if not (button.url and 'start=' in button.url):
            raise ValueError(f'Invalid data for {self.__class__.__name__} filter')

        start_param = button.url.split('start=')[-1]
        return f'/start {start_param}'

    def cast_update(self, update_obj: types.Message):
        return update_obj.text

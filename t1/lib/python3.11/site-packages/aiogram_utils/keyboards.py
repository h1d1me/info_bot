from __future__ import annotations

from copy import deepcopy

from aiogram import types


class KeyboardButton(types.KeyboardButton):

    def format(self, *args, **kwargs) -> KeyboardButton:
        """Return new button with formatted values."""
        new_button = deepcopy(self)

        for item, value in new_button.values.items():
            if isinstance(value, str):
                new_button[item] = value.format(*args, **kwargs)

        return new_button


class InlineKeyboardButton(types.InlineKeyboardButton):

    def format(self, *args, **kwargs) -> InlineKeyboardButton:
        """Return new button with formatted values."""
        new_button = deepcopy(self)

        for item, value in new_button.values.items():
            if isinstance(value, str):
                new_button[item] = value.format(*args, **kwargs)

        return new_button

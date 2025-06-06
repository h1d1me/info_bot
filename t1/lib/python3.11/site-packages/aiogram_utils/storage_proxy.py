from __future__ import annotations

import json
from typing import TypeVar, Generic

import mongoengine as me
from aiogram import Dispatcher
from aiogram.dispatcher import FSMContext
from mongoengine.base import BaseDocument

DocumentClass = TypeVar('DocumentClass')


class StorageProxy(Generic[DocumentClass]):

    def __init__(self, document_class: type[DocumentClass]):
        if not issubclass(document_class, BaseDocument):
            raise TypeError('document_class must be subclass of mongoengine.base.BaseDocument')

        self.document_class = document_class
        self.storage_field_name = document_class.__name__
        self._document = None

    @staticmethod
    def get_state() -> FSMContext:
        return Dispatcher.get_current().current_state()

    async def get_storage_data(self) -> dict:
        return await self.get_state().get_data()

    async def get_document(self) -> DocumentClass:
        if self._document is None:
            storage_data = await self.get_storage_data()
            self._document = self.document_class(**storage_data.get(self.storage_field_name, {}))
        return self._document

    async def update_storage_data(self):
        document: me.Document = await self.get_document()
        document_data: dict = json.loads(document.to_json())
        await self.get_state().update_data({self.storage_field_name: document_data})

    async def __aenter__(self) -> DocumentClass:
        return await self.get_document()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.update_storage_data()

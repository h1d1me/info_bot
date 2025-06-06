from aiogram.dispatcher.filters import BoundFilter


class StorageDataFilter(BoundFilter):
    """Check if all items matches the relevant items in the storage (for current User+Chat)."""

    key = 'storage'

    def __init__(self, dispatcher, filter_: dict):
        self.dispatcher = dispatcher
        self.filter_ = filter_

    def is_matching(self, storage: dict) -> bool:
        for key, value in self.filter_.items():
            if key not in storage:
                return False

            if value == '*':
                continue

            if isinstance(value, (list, tuple, set)) and storage[key] in value:
                continue

            if storage[key] == value:
                continue

            return False
        return True

    async def check(self, *_) -> bool:
        state = self.dispatcher.current_state()
        storage = await state.get_data()
        return self.is_matching(storage)

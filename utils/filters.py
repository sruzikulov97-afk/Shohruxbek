from aiogram.filters import BaseFilter
from aiogram.types import Message
from config import settings

class IsBoshAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user and message.from_user.id in settings.admin_list

class IsSklad(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user and message.from_user.id in settings.sklad_list

class IsAnyAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user and (message.from_user.id in settings.admin_list or message.from_user.id in settings.sklad_list)

import os
import asyncio

from telethon import TelegramClient, events, sync
from time import sleep, time
import logging


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


class TelegramAPIMock:

    def __init__(self, messages_list_mock: list[str] = [], sleep: float = 0.0):
        self.__messages_list_mock = messages_list_mock
        self.__sleep = sleep

    async def send_as_bot(self, message: str):
        print(message)

    async def yield_last_messages_from_chat(self, chat_id: int, limit: int = 5):
        for message in self.__messages_list_mock[:limit]:
            yield message
            await asyncio.sleep(self.__sleep)


class TelegramAPI:

    __api_requests_limit = {
        "requests": 20,
        "in_seconds": 60
    }

    __api_requests_limit_during_pump_detection = {
        "requests": 20,
        "in_seconds": 5
    }

    def __init__(self):

        self.__telethon_bot_name = os.environ.get("TELETHON_BOT_NAME", default="")
        self.__telethon_bot_token = os.environ.get("TELETHON_BOT_TOKEN", default="")
        self.__telethon_api_phone = os.environ.get("TELETHON_API_PHONE", default="")
        self.__telethon_api_id = os.environ.get("TELETHON_API_ID", default="")
        self.__telethon_api_hash = os.environ.get("TELETHON_API_HASH", default="")

        self.__user_id = int(os.environ.get("TELETHON_USER_ID", default=""))
        self.__bot_id = int(os.environ.get("TELETHON_BOT_ID", default=""))

        self.__user_client = TelegramClient(
            "user_session",
            self.__telethon_api_id,
            self.__telethon_api_hash
        ).start(
            phone = self.__telethon_api_phone
        )

        self.__bot_client = TelegramClient(
            "bot_session",
            self.__telethon_api_id,
            self.__telethon_api_hash
        ).start(
            bot_token = self.__telethon_bot_token
        )

    async def send_as_bot(self, message: str):
        print(message)
        await self.bot_client.send_message(
            self.__user_id,
            "[BOT] " + message
        )
        await asyncio.sleep(
            self.__api_requests_limit["in_seconds"] / self.__api_requests_limit["requests"]
        )

    async def yield_last_messages_from_chat(self, chat_id: int, limit: int = 5):

        for request_no in range(
            1,
            self.__api_requests_limit_during_pump_detection["requests"] + 1
        ):
            now = datetime.now().strftime("%H:%M:%S")
            print(f"request number -> {request_no} at {now}")

            for message in self.user_client.iter_messages(
                chat_id,
                limit = limit
            ):
                yield message
                await asyncio.sleep(
                    self.__api_requests_limit_during_pump_detection["in_seconds"] / self.__api_requests_limit_during_pump_detection["requests"]
                )



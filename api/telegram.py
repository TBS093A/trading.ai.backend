import os
import asyncio

from telethon import TelegramClient, events, sync
from time import sleep, time
from datetime import datetime, timezone
from collections import namedtuple

import logging


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


class TelegramAPIMock:

    def __init__(self, messages_list_mock: list[str] = [], sleep: float = 0.0):
        self.__messages_list_mock = self.__create_messages_mock(
            messages_list_mock = messages_list_mock
        )
        self.__sleep = sleep

    def __create_messages_mock(self, messages_list_mock: list[str]) -> list[dict]:
        prepared_telegram_messages = []
        Message = namedtuple("Message", ["id", "message"])
        for message in messages_list_mock:
            prepared_telegram_messages.append(
                Message(
                    id = -1,
                    message = message
                )
            )
        return prepared_telegram_messages

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
        )

        self.__bot_client = TelegramClient(
            "bot_session",
            self.__telethon_api_id,
            self.__telethon_api_hash
        )

    async def start(self):
        await self.__user_client.start(
            phone = self.__telethon_api_phone
        )
        await self.__bot_client.start(
            bot_token = self.__telethon_bot_token
        )

    async def stop(self):
        try:
            if await self.__user_client.is_connected():
                print("Closing User Client Telegram Session")
                self.__user_client.disconnect()
        except Exception as error:
            logging.error(error)
        try:
            if await self.__bot_client.is_connected():
                print("Closing Bot Client Telegram Session")
                self.__bot_client.disconnect()
        except Exception as error:
            logging.error(error)

    async def send_as_bot(self, message: str):
        print(message)
        await self.__bot_client.send_message(
            self.__user_id,
            "[BOT] " + message
        )
        await asyncio.sleep(
            self.__api_requests_limit["in_seconds"] / self.__api_requests_limit["requests"]
        )

    async def yield_last_messages_from_chat(self, chat_id: int, limit: int = 5) -> dict:
        """
        That Function Yield Messages Objects Which Can Be Trait As namedtuple:
            Message(
                id=4772,
                peer_id=PeerChannel(
                    channel_id=1625691880
                ),
                date=datetime.datetime(
                    2024, 11, 4, 19, 31, 37,
                    tzinfo=datetime.timezone.utc
                ),
                message='Next pump will be blah, blah, blah, [...]',
                out=False,
                mentioned=False,
                media_unread=False,
                silent=False,
                post=True,
                from_scheduled=False,
                legacy=False,
                edit_hide=False,
                pinned=False,
                noforwards=False,
                invert_media=False,
                offline=False,
                from_id=None,
                from_boosts_applied=None,
                saved_peer_id=None,
                fwd_from=None,
                via_bot_id=None,
                via_business_bot_id=None,
                reply_to=None,
                media=None,
                reply_markup=None,
                entities=[
                    MessageEntityBold(
                        offset=0,
                        length=41
                    )
                ],
                views=108181,
                forwards=3,
                replies=None,
                edit_date=None,
                post_author=None,
                grouped_id=None,
                reactions=None,
                restriction_reason=[],
                ttl_period=None,
                quick_reply_shortcut_id=None,
                effect=None,
                factcheck=None
            )
        """

        for request_no in range(
            1,
            self.__api_requests_limit_during_pump_detection["requests"] + 1
        ):
            now = datetime.now().strftime("%H:%M:%S")
            print(f"request number -> {request_no} at {now}")

            try:

                messages_generator = self.__user_client.iter_messages(
                    chat_id,
                    limit = limit
                )

            except:

                messages_generator = await self.__user_client.iter_messages(
                    chat_id,
                    limit = limit
                )

            async for message in messages_generator:
                print(f"yielded message:\n\n{message.message}\n")
                yield message
                await asyncio.sleep(
                    self.__api_requests_limit_during_pump_detection["in_seconds"] / self.__api_requests_limit_during_pump_detection["requests"]
                )



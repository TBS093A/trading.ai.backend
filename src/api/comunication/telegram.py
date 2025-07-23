import os
import asyncio

from telethon import TelegramClient, events, sync
from time import sleep, time
from datetime import datetime, timezone
from collections import namedtuple

import traceback
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
        "in_seconds": 2.5
    }

    def __init__(self,
        bot_name: str,
        bot_token: str,
        api_phone: str,
        api_id: str,
        api_hash: str,
        user_id: str,
        bot_id: str
    ):

        self.__telethon_bot_name = bot_name
        self.__telethon_bot_token = bot_token
        self.__telethon_api_phone = api_phone
        self.__telethon_api_id = api_id
        self.__telethon_api_hash = api_hash

        self.__user_id = user_id
        self.__bot_id = bot_id

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
            if self.__user_client.is_connected():
                print("Closing User Client Telegram Session")
                await self.__user_client.disconnect()
        except Exception as error:
            logging.error(f"'{error}' occured here:\n{traceback.format_exc()}")
        try:
            if self.__bot_client.is_connected():
                print("Closing Bot Client Telegram Session")
                await self.__bot_client.disconnect()
        except Exception as error:
            logging.error(f"'{error}' occured here:\n{traceback.format_exc()}")

    async def send_as_bot(self, message: str):
        print(message)
        await self.__bot_client.send_message(
            self.__user_id,
            "[BOT] " + message
        )
        await asyncio.sleep(
            self.__api_requests_limit["in_seconds"] / self.__api_requests_limit["requests"]
        )

    async def yield_last_messages_from_chat(self, chat_id: int, limit: int = 1, scheduled = False) -> dict:
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

            if request_no >= self.__api_requests_limit_during_pump_detection["requests"]:

                raise Exception(
                    f"Too Many Requests To Telegram API For Pumped Coin Name (Count: {request_no}, Limit: {self.__api_requests_limit_during_pump_detection['requests']})"
                )

            print(f"Request Number -> {request_no}")

            if request_no > 1:

                await asyncio.sleep(
                    self.__api_requests_limit_during_pump_detection["in_seconds"] / self.__api_requests_limit_during_pump_detection["requests"]
                )

            print(f"Download Latest Telegram Messages (Count: {limit})")

            try:

                messages_generator = self.__user_client.iter_messages(
                    chat_id,
                    limit = limit,
                    scheduled = scheduled
                )

            except:

                messages_generator = await self.__user_client.iter_messages(
                    chat_id,
                    limit = limit,
                    scheduled = scheduled
                )

            async for message in messages_generator:
                print(f"Yielded Message:\n\n{message.message}\n")
                yield message


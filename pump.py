# based on echobot:
# https://docs.python-telegram-bot.org/en/stable/examples.echobot.html
# more examples:
# https://docs.python-telegram-bot.org/en/stable/examples.html

### GENERAL NOTE:
### Telethon is better:
###     https://github.com/LonamiWebs/Telethon
### Telegram API / Application (api id / api hash):
###     https://my.telegram.org/apps

# user_id you can get from:
# https://api.telegram.org/bot<bot_token>/getUpdates
# firstly send message from your account to the bot, check link above and get your user id from result -> 0 -> message -> from -> id

import requests
import os
import re
import json
import asyncio
import logging

from pprint import pprint
from datetime import datetime, timedelta, timezone

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI
from api.telegram import TelegramAPI
from api.transactions.strategies import (
    DistributedRiskStaticQuoteAndAssetTransactionStrategy
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info

regexes = {
    "single_uppercase_word_without_spaces": r"^[A-Z0-9]+$",
    "single_word_without_spaces": r"^[^\s]+$",
}

exchange_apis = {
    "kucoin": KucoinAPI(
        api_key = os.environ.get("KUCOIN_API_KEY", default=""),
        api_secret =  os.environ.get("KUCOIN_API_SECRET", default=""),
        api_key_passphrase = os.environ.get("KUCOIN_API_KEY_PASSPHRASE", default="")
    ),
    "mexc": MexcAPI(
        api_key = os.environ.get("MEXC_API_KEY", default=""),
        api_secret = os.environ.get("MEXC_API_SECRET", default="")
    )
}

const_channels = {
    "Crypto Pump Club": {
        "username": "cryptoclubpump",
        "id": -1001625691880,
        "pumps": [
            #{
            #    "day": "tuesday",
            #    "time": "17:00:00",
            #    "zone": timezone(timedelta(0), "GMT"), # timezone(timedelta(0), "GMT") - for GMT / timezone.utc - for UTC / None - for LOCAL
            #    "is_today": False,
            #    "is_realised": False,
            #    "quote_availability_is_updated": False,
            #    "long_time_is_reported": False,
            #    "middle_time_is_reported": False,
            #},
            #{
            #    "day": "wednesday",
            #    "time": "17:00:00",
            #    "zone": timezone(timedelta(0), "GMT"), # timezone(timedelta(0), "GMT") - for GMT / timezone.utc - for UTC / None - for LOCAL
            #    "is_today": False,
            #    "is_realised": False,
            #    "quote_availability_is_updated": False,
            #    "long_time_is_reported": False,
            #    "middle_time_is_reported": False,
            #},
            {
                "day": "friday",
                "time": "17:00:00",
                "zone": timezone(timedelta(0), "GMT"), # timezone(timedelta(0), "GMT") - for GMT / timezone.utc - for UTC / None - for LOCAL
                "is_today": False,
                "is_realised": False,
                "quote_availability_is_updated": False,
                "long_time_is_reported": False,
                "middle_time_is_reported": False,
            },
        ],
        "exchange": exchange_apis["mexc"],
        "currency": "USDT",
        "strategy": DistributedRiskStaticQuoteAndAssetTransactionStrategy,
        "regex": regexes["single_uppercase_word_without_spaces"],
    }
}


class Pump:

    def __init__(
        self,
        channels: dict,
        telegram_api: TelegramAPI,
        loop_single_iteration_long_waiting_time = 60.0 * 25,
        loop_single_iteration_middle_waiting_time = 30.0,
        loop_single_iteration_short_waiting_time = 0.25,
        DEBUG: bool = False
    ):

        self.__DEBUG = DEBUG

        self.__channels = channels
        self.__loop_single_iteration_long_waiting_time = loop_single_iteration_long_waiting_time
        self.__loop_single_iteration_middle_waiting_time = loop_single_iteration_middle_waiting_time
        self.__loop_single_iteration_short_waiting_time = loop_single_iteration_short_waiting_time
        self.__telegram_api = telegram_api

        self.__used_transaction_strategies = {}

    def get_channels(self):
        return self.__channels

    def __gather_coin(self, captured_message: str, regex: str) -> str:
        match_pattern = re.match(
            regex,
            captured_message
        )
        if match_pattern:
            coin = match_pattern.group(0)
            if ' ' not in coin:
                if '$' in coin:
                    coin = coin.replace('$', '')
            return coin
        return None

    async def __sleep_to_next_day(self):
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        target_time_today = datetime.strptime(f'{today_str} 01:00:00', '%Y-%m-%d %H:%M:%S')

        if target_time_today <= now:
            target_time_today += timedelta(days=1)

        seconds_until_target = (target_time_today - now).total_seconds()

        print(f"Sleep {seconds_until_target}s To The Next Day (No Pumps Today)")

        if self.__DEBUG == False:

            await asyncio.sleep(seconds_until_target)


    async def __pump_investment(self):
        for channel_name, channel_info in self.__channels.items():

            for pump_info in channel_info['pumps']:

                if channel_name not in self.__used_transaction_strategies:

                    self.__used_transaction_strategies[channel_name] = channel_info["strategy"](
                        exchange_api = channel_info["exchange"],
                        telegram_api = self.__telegram_api,
                        currency = channel_info["currency"],
                        pump_time = pump_info["time"],
                        pump_time_zone = pump_info["zone"],
                        DEBUG = self.__DEBUG
                    )

                if pump_info['is_realised']:
                    continue

                now = datetime.now()

                if pump_info["zone"] != None:

                    now = datetime.now(
                        pump_info["zone"]
                    )

                current_day = now.strftime("%A")
                current_hour_and_minute = now.strftime("%H:%M:%S")[:5]

                if current_day.lower() == pump_info["day"].lower():

                    if pump_info['is_realised'] == False:

                        pump_info['is_today'] = True

                if pump_info['is_today'] == True:

                    if current_hour_and_minute == pump_info["time"][:5]:

                        print(f"Download messages from {channel_name} (USERNAME: {channel_info['username']} ID:, {channel_info['id']}) for pump at {pump_info['day']} {pump_info['time']} (timezone {pump_info['zone'] if pump_info['zone'] is not None else 'LOCAL'})")

                        async for message in self.__telegram_api.yield_last_messages_from_chat(
                            chat_id = channel_info['id']
                        ):

                            captured_coin = self.__gather_coin(
                                captured_message = message.message,
                                regex = channel_info["regex"]
                            )

                            if captured_coin == None:

                                print("No Coin Found!")

                            if captured_coin != None:

                                print(f"Captured Coin: {captured_coin}")

                                await self.__used_transaction_strategies[channel_name].invoke(
                                    coin = captured_coin,
                                    buy = True,
                                    sell = True,
                                )

                                pump_info['is_realised'] = True
                                pump_info['is_today'] = False
                                pump_info['quote_availability_is_updated'] = False
                                pump_info["middle_time_is_reported"] = False
                                pump_info["long_time_is_reported"] = False

                                del self.__used_transaction_strategies[channel_name]

                                break

                    if current_hour_and_minute != pump_info["time"][:5]:

                        if int(current_hour_and_minute[:2]) > int(pump_info["time"][:2]):

                            pump_info['is_today'] = False

                            break

                        current_time = datetime.strptime(current_hour_and_minute, "%H:%M")
                        pump_time = datetime.strptime(pump_info["time"][:5], "%H:%M")

                        time_difference = abs(pump_time - current_time)

                        if time_difference <= timedelta(minutes=1):

                            message = f"Wait {self.__loop_single_iteration_short_waiting_time}s To Today Pump ({channel_info['username']} -> ID: {channel_info['id']}, Time: {pump_info['time']}, Time Zone: {pump_info['zone'] if pump_info['zone'] is not None else 'LOCAL'})"

                            if pump_info['quote_availability_is_updated'] == False:

                                pump_info['quote_availability_is_updated'] = True

                                updated_quote_message = self.__used_transaction_strategies[channel_name].update_possible_buy_transactions()

                                await self.__telegram_api.send_as_bot(
                                    message = f"{ message }\n\n{ updated_quote_message }"
                                )

                            print(message)

                            await asyncio.sleep(self.__loop_single_iteration_short_waiting_time)

                        elif time_difference <= timedelta(minutes=30) and time_difference > timedelta(minutes=1):

                            message = f"Wait {self.__loop_single_iteration_middle_waiting_time}s To Today Pump ({channel_info['username']} -> ID: {channel_info['id']}, Time: {pump_info['time']}, Time Zone: {pump_info['zone'] if pump_info['zone'] is not None else 'LOCAL'})"

                            print(message)

                            if pump_info["middle_time_is_reported"] == False:

                                pump_info["middle_time_is_reported"] = True

                                await self.__telegram_api.send_as_bot(
                                    message = message
                                )

                            await asyncio.sleep(self.__loop_single_iteration_middle_waiting_time)

                        elif time_difference > timedelta(minutes=30):

                            message = f"Wait {self.__loop_single_iteration_long_waiting_time}s To Today Pump ({channel_info['username']} -> ID: {channel_info['id']}, Time: {pump_info['time']}, Time Zone: {pump_info['zone'] if pump_info['zone'] is not None else 'LOCAL'})"

                            print(message)

                            if pump_info["long_time_is_reported"] == False:

                                pump_info["long_time_is_reported"] = True

                                await self.__telegram_api.send_as_bot(
                                    message = message
                                )

                            await asyncio.sleep(self.__loop_single_iteration_long_waiting_time)

                if pump_info['is_today'] == False:

                    continue


    def __reset_channel_day_stats(self):
        for channel_name, channel_info in self.__channels.items():
            for pump_info in channel_info['pumps']:
                if pump_info['is_realised'] == True:
                    current_day = datetime.now().strftime("%A")
                    if current_day.lower() != pump_info['day'].lower():
                        pump_info['is_realised'] = False

    def __detect_some_pump_is_today(self):
        for channel_name, channel_info in self.__channels.items():
            for pump_info in channel_info['pumps']:
                if pump_info['is_today']:
                    return True
        return False

    async def capture_pump(self):
        while True:

            await self.__pump_investment()

            self.__reset_channel_day_stats()

            pump_is_today = self.__detect_some_pump_is_today()

            if pump_is_today == False:
                await self.__sleep_to_next_day()

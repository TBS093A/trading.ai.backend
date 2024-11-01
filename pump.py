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
import logging

from pprint import pprint
from datetime import datetime, timedelta

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI
from api.transactions.strategies import (
    DistributedRiskStaticQuoteAndAssetTransactionStrategy
)


# Temp

colon_pattern = r"[^:]+:\s*([^\r\n]+)"
kucoin_alone_token_in_string_pattern = r"^[A-Z0-9\$]+$"
kucoin_url_pattern = r"/trade/([A-Z]+)-USDT"
kucoin_pumps_binance_chat_pattern = r"^Selected COIN/TOKEN\s*:\s*(\$?\w+)$"

# Temp


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


class Pump:

    def __init__(self, DEBUG: bool = False):

        self.__DEBUG = DEBUG

        self.__telegram_api = TelegramAPI(
            DEBUG = DEBUG
        )

        self.__exchange_apis = {
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

        self.__transaction_strategies = {
            "DRSQAATS": DistributedRiskStaticQuoteAndAssetTransactionStrategy,
        }

        self.__channels = {
            "Crypto Pump Club": {
                "username": "cryptoclubpump",
                "id": -1001625691880,
                "pumps": [
                    {
                        "day": "sunday",
                        "time": "19:00:00",
                        "is_today": False,
                        "is_realised": False,
                    },
                ],
                "exchange": self.__exchange_apis["mexc"],
                "currency": "USDT",
                "strategy": self.__transaction_strategies["DRSQAATS"],
                "regex": r"",
            },
            "Xt Pumps VIP": {
                "username": "XtpumpsVip",
                "id": -1002129820268,
                "pumps": [
                    {
                        "day": "wednesday",
                        "time": "19:00:00",
                        "is_today": False,
                        "is_realised": False,
                    },
                ],
                "exchange": self.__exchange_apis["mexc"],
                "currency": "USDT",
                "strategy": self.__transaction_strategies["DRSQAATS"],
                "regex": r"",
            }
        }

    def __gather_coin(self, captured_message: str, regex: str) -> str:
        match_pattern = re.match(
            regex,
            captured_message
        )
        if match_pattern:
            coin = match_pattern.group(1)
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

        await asyncio.sleep(seconds_until_target)

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
            for channel_name, channel_info in self.__channels.items():
                for pump_info in channel_info['pumps']:
                    if pump_info['is_realised']:
                        continue
                    now = datetime.now()
                    current_day = now.strftime("%A")
                    current_hour_and_minute = now.strftime("%H:%M:%S")[:5]
                    if current_day.lower() == pump_info["day"].lower():
                        pump_info['is_today'] = True
                        if current_hour_and_minute == pump_info["time"][:5]:
                            print(f"Download messages from {channel_name} (USERNAME: {channel['username']} ID:, {channel['id']}) for pump at {pump['day']} {pump['time']}")

                            for message in self.__telegram_api.yield_last_messages_from_chat(
                                chat_id = chat
                            ):
                                match_results = self.__gather_coin(
                                    captured_message = captured_message,
                                    regex = channel_info["regex"]
                                )

                                if match_result != None:
                                    captured_coin = match_results.group(1)
                                    message = f"Captured Coin: {captured_coin}"

                                    await self.__telegram_api.send_as_bot(
                                        message = message
                                    )

                                    used_transaction_strategy = channel_info["strategy"](
                                        exchange_api = channel_info["exchange"],
                                        telegram_api = self.__telegram_api,
                                        DEBUG = self.__DEBUG
                                    )

                                    await used_transaction_strategy.invoke(
                                        coin = captured_coin,
                                        currency = channel_info["currency"],
                                        buy = True,
                                        sell = True,
                                    )

                                    pump_info['is_realised'] = True
                                    pump_info['is_today'] = False

                                    break

                        await asyncio.sleep(0.25)

            self.__reset_channel_day_stats()

            pump_is_today = self.__detect_some_pump_is_today()

            if pump_is_today == False:
                await self.__sleep_to_next_day()


async def main() -> None:


    await capture_pump()


if __name__ == "__main__":
    asyncio.run(main())

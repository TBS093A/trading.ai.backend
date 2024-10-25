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
from telethon import TelegramClient, events, sync

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI
from api.transactions.strategies import (
    DistributedRiskStaticQuoteAndAssetTransactionStrategy,
    DistributedRiskSummationTransactionStrategy,
    SingleShotAfterTimeTransactionStrategy,
)


telethon_bot_name = os.environ.get("TELETHON_BOT_NAME", default="")
telethon_bot_token = os.environ.get("TELETHON_BOT_TOKEN", default="")
telethon_api_phone = os.environ.get("TELETHON_API_PHONE", default="")
telethon_api_id = os.environ.get("TELETHON_API_ID", default="")
telethon_api_hash = os.environ.get("TELETHON_API_HASH", default="")

user_id = int(os.environ.get("TELETHON_USER_ID", default=""))
bot_id = int(os.environ.get("TELETHON_BOT_ID", default=""))

kucoin_api_key = os.environ.get("KUCOIN_API_KEY", default="")
kucoin_api_key_passphrase = os.environ.get("KUCOIN_API_KEY_PASSPHRASE", default="")
kucoin_api_secret = os.environ.get("KUCOIN_API_SECRET", default="")

mexc_api_key = os.environ.get("MEXC_API_KEY", default="")
mexc_api_secret = os.environ.get("MEXC_API_SECRET", default="")

kucoin_api = KucoinAPI(
    api_key = kucoin_api_key,
    api_secret = kucoin_api_secret,
    api_key_passphrase = kucoin_api_key_passphrase
)

mexc_api = MexcAPI(
    api_key = mexc_api_key,
    api_secret = mexc_api_secret
)



logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

colon_pattern = r"[^:]+:\s*([^\r\n]+)"
kucoin_alone_token_in_string_pattern = r"^[A-Z0-9\$]+$"
kucoin_url_pattern = r"/trade/([A-Z]+)-USDT"
kucoin_pumps_binance_chat_pattern = r"^Selected COIN/TOKEN\s*:\s*(\$?\w+)$"

commands = {
    "/!settings": {
        "regex": r'^/!settings exchange (\w+) transaction_strategy (\w+) used_currency (\w+) allow_manual_sell (\w+)$',
    },
    "/!buy": {
        "regex": r'^/!buy coin (\w+)$',
    },
    "/!sell": {
        "regex": r'^/!sell$'
    }
}

channels = {
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
        "exchange": mexc_api,
        "currency": "USDT",
        "strategy": DistributedRiskStaticQuoteAndAssetTransactionStrategy,
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
        "exchange": mexc_api,
        "currency": "USDT",
        "strategy": DistributedRiskSummationTransactionStrategy,
        "regex": r"",
    }
}


telegram_requests_per_minute_limit: int = 20

sec_time_for_check_messages: int = 5


async def send_as_bot(api_id, api_hash, bot_session, user, message):
    print(message)
    await bot_session.send_message(
        user,
        "[BOT] " + message
    )

def remove_settings():
    settings_file = 'settings.txt'
    if os.path.exists(settings_file):
        os.remove(settings_file)
        print("Settings file removed.")
    else:
        print("Settings file does not exist.")

def save_settings(settings_data):
    with open('settings.txt', 'w') as file:
        for key, value in settings_data.items():
            file.write(f"{key}: {value}\n")

def load_settings():
    settings_data = {}
    try:
        with open('settings.txt', 'r') as file:
            for line in file:
                key, value = line.strip().split(': ')
                settings_data[key] = value
        return settings_data
    except Exception as error:
        print(error)
        print("invoke with defaults")
        return {
            "exchange": "MEXC",
            "transaction_strategy": "DRSTS", #"SSATTS",
            "used_currency": "USDT",
            "allow_manual_sell": "FALSE",
        }


def gather_coin(captured_message: str, regex: str) -> str:
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


def gather_command(captured_message: str) -> str:
    for match_pattern_name, match_pattern_info in commands.items():
        match_pattern = re.match(
            manual_pattern_info["regex"],
            captured_message
        )
        if match_pattern_name == "match_setting":
           if match_pattern:

                exchange, strategy, currency, allow_manual_sell = match_pattern.groups()

                settings_data = {
                    "exchange": exchange,
                    "transaction_strategy": strategy,
                    "used_currency": currency,
                    "allow_manual_sell": allow_manual_sell,
                }

                remove_settings()

                save_settings(
                    settings_data = settings_data
                )

                print(f"Settings:\n\n{ settings_data }\n\nSaved!")

                return settings_data

        if match_pattern_name == "match_buy":
            if match_pattern:
                coin = match_pattern.group(1)
                if ' ' not in coin:
                    if '$' in coin:
                        coin = coin.replace('$', '')
                    overrided_settings = load_settings()
                    overrided_settings['coin'] = coin
                    remove_settings()
                    save_settings(
                        settings_data = overrided_settings
                    )

                    print(f"Buy Action:\n\nLoaded Settings:\n\n{ overrided_settings }\n\nLoaded!")

                    return dict(
                        {
                            "action": "buy"
                        },
                        **overrided_settings
                    )
        if match_pattern_name == "match_sell":
            if match_pattern:
                loaded_settings = load_settings()

                print(f"Sell Action:\n\nLoaded Settings:\n\n{ overrided_settings }\n\nLoaded!")

                return dict(
                    {
                        "action": "sell"
                    },
                    **loaded_settings
                )
    return None


async def sleep_to_next_day():
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    target_time_today = datetime.strptime(f'{today_str} 01:00:00', '%Y-%m-%d %H:%M:%S')

    if target_time_today <= now:
        target_time_today += timedelta(days=1)

    seconds_until_target = (target_time_today - now).total_seconds()

    await asyncio.sleep(seconds_until_target)


@client.on(events.NewMessage(pattern="(.*)"))
async def handler_coin(event):
    captured_message = event.message.message
    if "[BOT]" not in captured_message:
        await send_as_bot(
            telethon_api_id,
            telethon_api_hash,
            bot,
            user=user_id,
            message=f"Captured Message: {captured_message}"
        )

        match_results = gather_command(
            captured_message
        )

        if match_results != None and "action" not in match_results.keys():
            await send_as_bot(
                telethon_api_id,
                telethon_api_hash,
                bot,
                user=user_id,
                message=f"Settings:\n{ match_results }\nSaved!"
            )

        if match_results != None and "action" in match_results.keys():

            captured_coin = match_results["coin"]

            allow_manual_sell = match_results["allow_manual_sell"].lower() == "true"

            await send_as_bot(
                telethon_api_id,
                telethon_api_hash,
                bot,
                user=user_id,
                message=f"Captured Coin: {captured_coin}"
            )

            used_api = mexc_api

            if match_results["exchange"] == "KUCOIN":
                used_api = kucoin_api
            if match_results["exchange"] == "MEXC":
                used_api = mexc_api

            used_transaction_strategy = DistributedRiskSummationTransactionStrategy(
                api = used_api,
                telegram_client_credentials = {
                    "api_id": telethon_api_id,
                    "api_hash": telethon_api_hash,
                    "bot_session": bot,
                    "user": user_id
                },
                telegram_sending_method = send_as_bot
            )
            if match_results["transaction_strategy"] == "DRSTS":
                used_transaction_strategy = DistributedRiskSummationTransactionStrategy(
                    api = used_api,
                    telegram_client_credentials = {
                        "api_id": telethon_api_id,
                        "api_hash": telethon_api_hash,
                        "bot_session": bot,
                        "user": user_id
                    },
                    telegram_sending_method = send_as_bot
                )

            if match_results["transaction_strategy"] == "SSATTS":
                used_transaction_strategy = SingleShotAfterTimeTransactionStrategy(
                    api = used_api,
                    telegram_client_credentials = {
                        "api_id": telethon_api_id,
                        "api_hash": telethon_api_hash,
                        "bot_session": bot,
                        "user": user_id
                    },
                    telegram_sending_method = send_as_bot
                )


            if match_results["action"] == "buy":

                await used_transaction_strategy.invoke(
                    coin = captured_coin,
                    currency = match_results["used_currency"],
                    buy = True,
                    sell = not allow_manual_sell,
                )

                if allow_manual_sell:
                    await send_as_bot(
                        telethon_api_id,
                        telethon_api_hash,
                        bot,
                        user=user_id,
                        message=f"[Exchange Symbol Chart]({ used_api.generate_symbol_url() })"
                    )

            if match_results["action"] == "sell":

                await used_transaction_strategy.invoke(
                    coin = captured_coin,
                    currency = match_results["used_currency"],
                    buy = False,
                    sell = True,
                )


async def main() -> None:

    with TelegramClient(
        "user_session",
        telethon_api_id,
        telethon_api_hash
    ).start(
        phone=telethon_api_phone
    ) as client:

        bot = TelegramClient(
            "bot_session",
            telethon_api_id,
            telethon_api_hash
        ).start(
            bot_token=telethon_bot_token
        )

        #await send_as_bot(
        #    telethon_api_id,
        #    telethon_api_hash,
        #    bot,
        #    user=user_id,
        #    message=f"Bot Ready To Use!!!\n\nInstruction:\n\n\tSettings Init / Overriding Example:\n\n\t\t/!settings exchange:MEXC transaction_strategy:DRSTS used_currency:USDT allow_manual_sell=FALSE\n\n\tBuy Action Example:\n\n\t\t/!buy coin:ZZZ\n\n\tSell Action Example:\n\n\t\t/!sell"
        #)

        async while True:
            async for channel_name, channel_info in channels.items():
                async for pump_info in channel_info['pumps']:
                    if pump_info['is_realised']:
                        continue
                    now = datetime.now()
                    current_day = now.strftime("%A")
                    current_hour_and_minute = now.strftime("%H:%M:%S")[:5]
                    if current_day.lower() == pump_info["day"].lower():
                        pump_info['is_today'] = True
                        if current_hour_and_minute == pump_info["time"][:5]:
                            print(f"Download messages in {channel_name} (USERNAME: {channel['username']} ID:, {channel['id']}) for pump at {pump['day']} {pump['time']}")
                            async for request_no in range(1, telegram_requests_per_minute_limit + 1):
                                now = datetime.now().strftime("%H:%M:%S")
                                print(f"request no {request_no} at {now}")
                                async for message in client.iter_messages(chat, limit=5):
                                    match_results = gather_coin(
                                        captured_message = captured_message,
                                        regex = channel_info["regex"]
                                    )
                                    if match_result != None:

                                        captured_coin = match_results.group(1)

                                        await send_as_bot(
                                            telethon_api_id,
                                            telethon_api_hash,
                                            bot,
                                            user=user_id,
                                            message=f"Captured Coin: {captured_coin}"
                                        )

                                        used_exchange = channel_info["exchange"]

                                        used_transaction_strategy = channel_info["strategy"](
                                            api = used_api,
                                            telegram_client_credentials = {
                                                "api_id": telethon_api_id,
                                                "api_hash": telethon_api_hash,
                                                "bot_session": bot,
                                                "user": user_id
                                            },
                                            telegram_sending_method = send_as_bot
                                        )

                                        await used_transaction_strategy.invoke(
                                            coin = captured_coin,
                                            currency = channel_info["currency"],
                                            buy = True,
                                            sell = True,
                                        )

                                        pump_info['is_realised'] = True
                                        break

                                if pump_info['is_realised']:
                                    break
                                else:
                                    waiting_time = float(sec_time_for_check_messages / telegram_requests_per_minute_limit)
                                    await asyncio.sleep(waiting_time)
                        await asyncio.sleep(0.25)

            async for channel_name, channel_info in channels.items():
                async for pump_info in channel_info['pumps']:
                    if pump_info['is_realised'] == True:
                        current_day = datetime.now().strftime("%A")
                        if current_day.lower() != pump_info['day'].lower():
                            pump_info['is_realised'] = False

            pump_is_not_today = False

            async for channel_name, channel_info in channels.items():
                async for pump_info in channel_info['pumps']:
                    if pump_info['is_today'] == False:
                        pump_info['is_today'] = False
                        pump_is_not_today = True

            if pump_is_not_today:
                await sleep_to_next_day()

if __name__ == "__main__":
    asyncio.run(main())

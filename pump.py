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
from telethon import TelegramClient, events, sync

from api.kucoin import KucoinAPI
from api.mexc import MexcAPI
from api.transactions.strategies import (
    DistributedRiskSummationTransactionStrategy,
    SingleShotTransactionStrategy,
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

manual_pattern_settings = r'^/!settings exchange:(\w+) transaction_strategy:(\w+) used_currency:(\w+) allow_manual_sell=(\w+)$'

manual_pattern_buy = r'^/!buy coin:(\w+)$'

manual_pattern_sell = r'^/!sell$'


async def send_as_bot(api_id, api_hash, bot_session, user, message):
    print(message)
    await bot_session.send_message(
        user,
        "[BOT] " + message
    )

def save_settings(settings_data):
    with open('settings.txt', 'w') as file:
        for key, value in settings_data.items():
            file.write(f"{key}: {value}\n")

def load_settings():
    settings_data = {}
    with open('settings.txt', 'r') as file:
        for line in file:
            key, value = line.strip().split(': ')
            settings_data[key] = value
    return settings_data

def gather_coin_name(captured_message: str) -> str:

    match_patterns = {
        "match_settings": re.match(
            manual_pattern_settings,
            captured_message
        ),
        "match_buy": re.match(
            manual_pattern_buy,
            captured_message
        ),
        "match_sell": re.match(
            manual_pattern_sell,
            captured_message
        )
        #"match_coin_from_kucoin_pumps_binance_chat": re.match(
        #    kucoin_pumps_binance_chat_pattern,
        #    captured_message
        #),
        #"match_coin_from_url": re.match(
        #    kucoin_url_pattern,
        #    captured_message
        #),
        #"match_coin_from_one_word_message": re.match(
        #    kucoin_alone_token_in_string_pattern,
        #    captured_message
        #),
        #"match_coin_after_colon": re.match(
        #    colon_pattern,
        #    captured_message
        #)
    }

    for match_pattern_name, match_pattern in match_patterns.items():
        if match_pattern_name == "match_setting":
           if match_pattern:

                exchange, strategy, currency, allow_manual_sell = match_pattern.groups()

                save_settings(
                    settings_data = {
                        "exchange": exchange,
                        "transaction_strategy": strategy,
                        "used_currency": currency,
                        "allow_manual_sell": allow_manual_sell,
                    }
                )

                return None

        if match_pattern_name == "match_buy":
            if match_pattern:
                coin = match_pattern.group(1)
                if ' ' not in coin:
                    if '$' in coin:
                        coin = coin.replace('$', '')
                    overrided_settings = dict(
                        {
                            "coin": coin
                        },
                        **load_settings()
                    )
                    save_settings(
                        settings_data = overrided_settings
                    )
                    return dict(
                        {
                            "action": "buy"
                        },
                        **overrided_settings
                    )
        if match_pattern_name == "match_sell":
            if match_pattern:
                loaded_settings = load_settings()
                return dict(
                    {
                        "action": "sell"
                    },
                    **loaded_settings
                )

    return None


def main() -> None:
    """Start the bot."""
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

        await send_as_bot(
            telethon_api_id,
            telethon_api_hash,
            bot,
            user=user_id,
            message=f"Bot Ready To Use!!!\n\nInstruction:\n\n\tSettings Init / Overriding Example:\n\n\t\t/!settings exchange:MEXC transaction_strategy:DRSTS used_currency:USDT allow_manual_sell=FALSE\n\n\tBuy Action Example:\n\n\t\t/!buy coin:ZZZ\n\n\tSell Action Example:\n\n\t\t/!sell"
        )

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

                match_results = gather_coin_name(
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

                    #if match_results["transaction_strategy"] == "SSTS":
                    #    used_transaction_strategy = SingleShotTransactionStrategy(
                    #        api = used_api,
                    #        telegram_client_credentials = {
                    #            "api_id": telethon_api_id,
                    #            "api_hash": telethon_api_hash,
                    #            "bot_session": bot,
                    #            "user": user_id
                    #        },
                    #        telegram_sending_method = send_as_bot
                    #    )


                    if match_results["action"] == "buy":

                        await transaction_strategy.invoke(
                            coin = captured_coin,
                            currency = match_results["used_currency"],
                            buy = True,
                            sell = !allow_manual_sell,
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

                        await transaction_strategy.invoke(
                            coin = captured_coin,
                            currency = match_results["used_currency"],
                            buy = False,
                            sell = True,
                        )


        # Run the client until Ctrl+C is pressed, or the client disconnects
        print('(Press Ctrl+C to stop)')
        client.run_until_disconnected()


if __name__ == "__main__":
    main()

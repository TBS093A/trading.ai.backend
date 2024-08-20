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
from api.transactions.strategies import DistributedRiskSummationTransactionStrategy


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


async def send_as_bot(api_id, api_hash, bot_session, user, message):
    print(message)
    await bot_session.send_message(
        user,
        "[BOT] " + message
    )

def gather_coin_name(captured_message: str) -> str:

    match_patterns = {
        "match_coin_from_kucoin_pumps_binance_chat": re.match(
            kucoin_pumps_binance_chat_pattern,
            captured_message
        )
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

    for match_pattern_name, match_coin in match_patterns.items():
        if match_coin:
            coin = match_coin.group(1)
            if ' ' not in coin:
                if '$' in coin:
                    coin = coin.replace('$', '')
                return {
                    "match_pattern_name": match_pattern_name,
                    "coin": coin
                }
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

                match_coin = gather_coin_name(
                    captured_message
                )

                if match_coin != None:
                    captured_coin = match_coin["coin"]
                    await send_as_bot(
                        telethon_api_id,
                        telethon_api_hash,
                        bot,
                        user=user_id,
                        message=f"Captured Coin: {captured_coin}\nUsed Match Pattern: { match_coin['match_pattern_name'] }"
                    )

                    transaction_strategy = DistributedRiskSummationTransactionStrategy(
                        api = mexc_api,
                        telegram_client_credentials = {
                            "api_id": telethon_api_id,
                            "api_hash": telethon_api_hash,
                            "bot_session": bot,
                            "user": user_id
                        },
                        telegram_sending_method = send_as_bot
                    )

                    await transaction_strategy.invoke(
                        coin = captured_coin,
                        currency = "USDT"
                    )

        # Run the client until Ctrl+C is pressed, or the client disconnects
        print('(Press Ctrl+C to stop)')
        client.run_until_disconnected()


if __name__ == "__main__":
    main()

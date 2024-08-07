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


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

pattern = r"[^:]+:\s*([^\r\n]+)"

async def send_as_bot(api_id, api_hash, bot_session, user, message):
    await bot_session.send_message(user, message)


def main() -> None:
    """Start the bot."""
    telethon_bot_name = os.environ.get("TELETHON_BOT_NAME", default="")
    telethon_bot_token = os.environ.get("TELETHON_BOT_TOKEN", default="")
    telethon_api_phone = os.environ.get("TELETHON_API_PHONE", default="")
    telethon_api_id = os.environ.get("TELETHON_API_ID", default="")
    telethon_api_hash = os.environ.get("TELETHON_API_HASH", default="")

    user_id = 6687530364
    bot_id = 7411839891

    kucoin_api_key = os.environ.get("KUCOIN_API_KEY", default="")
    kucoin_api_key_passphrase = os.environ.get("KUCOIN_API_KEY_PASSPHRASE", default="")
    kucoin_api_secret = os.environ.get("KUCOIN_API_HASH", default="")

    kucoin_api = KucoinAPI(
        api_key = kucoin_api_key,
        api_secret = kucoin_api_secret,
        api_key_passphrase = kocoin_api_key_passphrase
    )

    with TelegramClient("user_session", telethon_api_id, telethon_api_hash).start(phone=telethon_api_phone) as client:
        bot = TelegramClient("bot_session", telethon_api_id, telethon_api_hash).start(bot_token=telethon_bot_token)
        # Register the update handler so that it gets called
        # client.add_event_handler(handler)
        @client.on(events.NewMessage(pattern="(.*)"))
        async def handler_coin(event):
            captured_message = event.message.message
            if "[BOT]" not in captured_message or "Captured Message:" not in captured_message or "Captured Coin:" not in captured_message:
                print(f"Recivied Message: {captured_message}")
                await send_as_bot(
                    telethon_api_id,
                    telethon_api_hash,
                    bot,
                    user=user_id,
                    message=f"[BOT] Captured Message: {captured_message}"
                )
                #await client.send_message("tbs_pump_bot", f"Catched Message: {catched_message}")
                match_coin = re.match(pattern, captured_message)
                if match_coin:
                    captured_coin = match_coin.group(1)
                    print(f"Recivied Coin: {captured_coin}")
                    await send_as_bot(
                        telethon_api_id,
                        telethon_api_hash,
                        bot,
                        user=user_id,
                        message=f"[BOT] Captured Coin: {captured_coin}"
                    )
                    #await client.send_message("tbs_pump_bot", f"Coin Which Will Pumped: {captured_coin}")
                #await event.respond('Hey!')

        # Run the client until Ctrl+C is pressed, or the client disconnects
        print('(Press Ctrl+C to stop)')
        client.run_until_disconnected()


if __name__ == "__main__":
    main()

# based on echobot:
# https://docs.python-telegram-bot.org/en/stable/examples.echobot.html
# more examples:
# https://docs.python-telegram-bot.org/en/stable/examples.html

### GENERAL NOTE:
### Telethon is better:
###     https://github.com/LonamiWebs/Telethon
### Telegram API / Application (api id / api hash):
###     https://my.telegram.org/apps

import requests
import os
import json
import logging

from pprint import pprint
from telethon import TelegramClient, events, sync


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the bot."""
    api_id = os.environ.get("TELETHON_API_ID", default="")
    api_hash = os.environ.get("TELETHON_API_HASH", default="")

    with TelegramClient("pump", api_id, api_hash, proxy=None) as client:
        # Register the update handler so that it gets called
        # client.add_event_handler(handler)
        @client.on(events.NewMessage(pattern='(?i)hi|hello'))
        async def handler(event):
            catched_message = event.message.message
            print(f"recivied message: {catched_message}")
            #await event.respond('Hey!')
            await client.send_message("PumpBot", f"recivied message: {catched_message}")

        # Run the client until Ctrl+C is pressed, or the client disconnects
        print('(Press Ctrl+C to stop this)')
        client.run_until_disconnected()


if __name__ == "__main__":
    main()

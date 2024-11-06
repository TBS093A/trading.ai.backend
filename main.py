import asyncio
import logging

from pump import (
    const_channels,
    Pump
)
from api.telegram import TelegramAPI


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info


async def main() -> None:

    try:

        telegram_api = TelegramAPI()

        pump = Pump(
            channels = const_channels,
            telegram_api = telegram_api,
        )

        await pump.capture_pump()

    except Exception as error:

        print(f"closed by issue:\n\n{error}")

    except KeyboardInterrupt as error:

        print(f"closed by user keyboard interrupt:\n\n{error}")

        try:

            del telegram_api

        except Exception as cleanup_error:

            print(f"error at cleanup: {cleanup_error}")

    finally:

        try:

            del telegram_api

        except Exception as cleanup_error:

            print(f"error at finally cleanup: {cleanup_error}")


if __name__ == "__main__":

    try:

        async_loop = asyncio.get_event_loop()

        async_loop.run_until_complete(main())

    except Exception as error:

        print(f"error at async loop: {error}")

    finally:

        async_loop.close()

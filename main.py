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

        await telegram_api.start()

        pump = Pump(
            channels = const_channels,
            telegram_api = telegram_api,
        )

        await pump.capture_pump()

    except Exception as error:

        logging.error(f"closed by issue:\n\n{error}")

    except KeyboardInterrupt as error:

        logging.warning(f"closed by user keyboard interrupt:\n\n{error}")

        try:

            await telegram_api.stop()

        except Exception as cleanup_error:

            logging.error(f"error at cleanup: {cleanup_error}")

    finally:

        try:

            await telegram_api.stop()

        except Exception as cleanup_error:

            logging.error(f"error at finally cleanup: {cleanup_error}")


if __name__ == "__main__":
    try:
        try:

            async_loop = asyncio.get_running_loop()

        except RuntimeError:

            async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(async_loop)

        async_loop.run_until_complete(main())

    except asyncio.CancelledError:

        logging.warning("Async tasks were cancelled")

    except Exception as error:

        logging.error(f"Unexpected error in async loop: {error}", exc_info=True)

    finally:

        pending_tasks = asyncio.all_tasks(async_loop)
        if pending_tasks:
            for task in pending_tasks:
                task.cancel()
            async_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))

        async_loop.close()

from pump import (
    const_channels,
    Pump
)
from api.telegram import TelegramAPI


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

            print("error at cleanup: {cleanup_error}")

    finally:

        try:

            del telegram_api

        except Exception as cleanup_error:

            print("error at finally cleanup: {cleanup_error}")

if __name__ == "__main__":
    asyncio.run(main())

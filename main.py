from pump import (
    const_channels,
    Pump
)
from api.telegram import TelegramAPI


async def main() -> None:

    pump = Pump(
        channels = const_channels,
        telegram_api = TelegramAPI(),
    )

    await pump.capture_pump()


if __name__ == "__main__":
    asyncio.run(main())

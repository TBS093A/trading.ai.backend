import asyncio
import logging
import traceback
import os

from pump import (
    const_channels,
    Pump
)
from api.telegram import TelegramAPI
from api.openai import OpenaiAPI
from api.mexc import MexcAPI
from ai.analysis import TechnicalAnalysis


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print = logging.info

# Konfiguracja kanałów do analizy technicznej
technical_analysis_channels = {
    "Crypto Analysis Channel": {
        "username": "cryptoanalysis",
        "id": -1001234567890,  # Zastąp prawdziwym ID kanału
    },
    # Dodaj więcej kanałów według potrzeb
}

async def main() -> None:
    try:
        telegram_api = TelegramAPI()
        openai_api = OpenaiAPI()
        mexc_api = MexcAPI(
            api_key=os.environ.get("MEXC_API_KEY", default=""),
            api_secret=os.environ.get("MEXC_API_SECRET", default="")
        )

        await telegram_api.start()

        # Inicjalizacja analizy technicznej
        technical_analysis = TechnicalAnalysis(
            telegram_api=telegram_api,
            openai_api=openai_api,
            mexc_api=mexc_api,
            channels=technical_analysis_channels
        )

        # Rejestracja handlerów dla analizy technicznej
        technical_analysis.register_handlers()

        # Inicjalizacja bota pump
        pump = Pump(
            channels=const_channels,
            telegram_api=telegram_api,
        )

        # Uruchomienie bota pump
        await pump.capture_pump()

    except Exception as error:
        logging.error(f"closed by issue:\n\n'{error}' ->\n{traceback.format_exc()}")

    except KeyboardInterrupt as error:
        logging.warning(f"closed by user keyboard interrupt:\n\n{error} ->\n{traceback.format_exc()}")

        try:
            await telegram_api.stop()
        except Exception as cleanup_error:
            logging.error(f"error at cleanup: {cleanup_error} ->\n{traceback.format_exc()}")

    finally:
        try:
            await telegram_api.stop()
        except Exception as cleanup_error:
            logging.error(f"error at finally cleanup: {cleanup_error} ->\n{traceback.format_exc()}")


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

        logging.error(f"Unexpected error in async loop: {error} ->\n{traceback.format_exc()}", exc_info=True)

    finally:

        pending_tasks = asyncio.all_tasks(async_loop)
        if pending_tasks:
            for task in pending_tasks:
                task.cancel()
            async_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))

        async_loop.close()

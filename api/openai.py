import os
import asyncio
import logging
import traceback
import openai

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class OpenaiAPI:

    def __init__(self):
        openai.api_key = os.environ.get("OPENAI_API_KEY", default="")
        self.override_message_content = """
            Please rate that message as True (if message described LONG or HODL operation) or as False (if message described SHORT operation).
            Please give only boolean response for that classification.
            Thanks in advance.
        """

    async def send_message(self, message: str) -> dict:
        try:

            overridden_message = f"{ self.override_message_content }\nContent:\n{ message }"

            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": overridden_message
                    }
                ]
            )

            return {
                "message": response.choices[0].message["content"]
            }

        except Exception as error:
            logger.error(f"Error while sending message: {error} ->\n{traceback.format_exc()}")

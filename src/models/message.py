from models.activity import Activity
from services.bots import telegram
from utils import formatter
from config import MESSAGE_TASK_INTERVAL, TRY_AGAIN_INTERVAL
from aiogram.exceptions import TelegramAPIError
from loguru import logger
from colorama import Fore
import asyncio, hashlib

class Message:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.message_id = None
        self.last_task = None
        self.last_img_hash = None

    async def run_task(self, act: Activity):
        if self.last_task:
            self.last_task.cancel()
            logger.trace("Task canceled.")
        self.last_task = asyncio.create_task(self.handle(act))
        logger.trace("Task started.")

    async def pause(self):
        if self.last_task:
            self.last_task.cancel()
        try:
            if self.message_id:
                await telegram.delete_message(self.chat_id, self.message_id)
        except: pass
        self.message_id = None
        logger.trace("Task stopped.")

    async def handle(self, act: Activity):
        try:
            small_hash = hashlib.md5(str(act.assets.small_image_url).encode('utf-8')).hexdigest()
            while True:
                try:
                    if self.message_id is None:
                        self.message_id = await telegram.send_message(self.chat_id, formatter.get_message_text(act), act.assets.get_small_image())
                        self.last_img_hash = small_hash
                    else:
                        if act.assets.small_image_url:
                            if self.last_img_hash != small_hash:
                                await telegram.edit_media(self.chat_id, self.message_id, formatter.get_message_text(act), act.assets.get_small_image())
                                self.last_img_hash = small_hash
                            else:
                                await telegram.edit_media(self.chat_id, self.message_id, formatter.get_message_text(act))
                        else:
                            try:
                                await telegram.edit_text(self.chat_id, self.message_id, formatter.get_message_text(act))
                            except Exception:
                                # If editing raw text fails, attempt an edit_media fallback instead of deleting
                                await telegram.edit_media(self.chat_id, self.message_id, formatter.get_message_text(act))
                            self.last_img_hash = None
                except TelegramAPIError as ex:
                    logger.error(f"Telegram API Error during edit: {ex}")
                    await asyncio.sleep(TRY_AGAIN_INTERVAL)

                except Exception as ex:
                    # STRICT EDIT MODE: instead of deleting and recreating the message here,
                    # log the formatting error, keep the message ID, and wait for the next tick.
                    logger.error(f"Formatting or playback edit failed: {ex}")
                    await asyncio.sleep(TRY_AGAIN_INTERVAL)

                await asyncio.sleep(MESSAGE_TASK_INTERVAL)
        except: 
            pass

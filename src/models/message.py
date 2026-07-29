from models.activity import Activity
from services.bots import telegram
from utils import formatter
from config import MESSAGE_TASK_INTERVAL, TRY_AGAIN_INTERVAL
from aiogram.exceptions import TelegramAPIError
from loguru import logger
from colorama import Fore
import asyncio, hashlib, json, os

STATE_FILE = ".last_message.json"

def save_state(chat_id: int, message_id: int | None):
    try:
        if message_id:
            with open(STATE_FILE, "w") as f:
                json.dump({"chat_id": chat_id, "message_id": message_id}, f)
        elif os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception as e:
        logger.trace(f"Error saving state file: {e}")

def load_state() -> dict | None:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None

class Message:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.message_id = None
        self.last_task = None
        self.last_img_hash = None

    async def cleanup_orphan(self):
        state = load_state()
        if state:
            try:
                await telegram.delete_message(state["chat_id"], state["message_id"])
                logger.info(f"Cleaned up orphan message ID: {state['message_id']}")
            except Exception as e:
                logger.trace(f"Could not delete orphan message: {e}")
            finally:
                save_state(self.chat_id, None)

    def update_message_id(self, new_id: int | None):
        self.message_id = new_id
        save_state(self.chat_id, new_id)

    async def run_task(self, act: Activity):
        if self.last_task:
            self.last_task.cancel()
            try:
                await self.last_task
            except asyncio.CancelledError:
                pass
            logger.trace("Task canceled.")

        # Always delete the old message on activity change to force a brand new post
        if self.message_id:
            try:
                await telegram.delete_message(self.chat_id, self.message_id)
            except Exception as e:
                logger.trace(f"Failed to delete old message on activity change: {e}")
            finally:
                self.update_message_id(None)
        else:
            await self.cleanup_orphan()

        self.last_task = asyncio.create_task(self.handle(act))
        logger.trace("Task started.")

    async def pause(self):
        if self.last_task:
            self.last_task.cancel()
        try:
            if self.message_id:
                await telegram.delete_message(self.chat_id, self.message_id)
        except Exception as e:
            logger.trace(f"Pause delete exception ignored: {e}")
        finally:
            self.update_message_id(None)
            logger.trace("Task stopped.")

    async def handle(self, act: Activity):
        try:
            if self.message_id is None:
                await self.cleanup_orphan()

            small_hash = hashlib.md5(str(act.assets.small_image_url).encode('utf-8')).hexdigest() if act.assets.small_image_url else None
            
            while True:
                try:
                    text_content = formatter.get_message_text(act)

                    if self.message_id is None:
                        # Ensures lingering state is wiped before posting new message
                        await self.cleanup_orphan()

                        new_id = await telegram.send_message(self.chat_id, text_content, act.assets.get_small_image())
                        self.update_message_id(new_id)
                        self.last_img_hash = small_hash
                    else:
                        # Updates timestamp/duration in-place while staying on the exact same song/game
                        if act.assets.small_image_url:
                            if self.last_img_hash != small_hash:
                                await telegram.edit_media(self.chat_id, self.message_id, text_content, act.assets.get_small_image())
                                self.last_img_hash = small_hash
                            else:
                                try:
                                    await telegram.edit_media(self.chat_id, self.message_id, text_content)
                                except TelegramAPIError:
                                    await telegram.edit_text(self.chat_id, self.message_id, text_content)
                        else:
                            try:
                                await telegram.edit_text(self.chat_id, self.message_id, text_content)
                            except TelegramAPIError:
                                try:
                                    await telegram.edit_media(self.chat_id, self.message_id, text_content)
                                except TelegramAPIError:
                                    pass
                            self.last_img_hash = None

                except TelegramAPIError as ex:
                    logger.error(f"Telegram API Error during edit: {ex}")
                    if "message to edit not found" in str(ex).lower():
                        self.update_message_id(None)
                    await asyncio.sleep(TRY_AGAIN_INTERVAL)

                except Exception as ex:
                    logger.error(f"Formatting or playback edit failed: {ex}")
                    await asyncio.sleep(TRY_AGAIN_INTERVAL)

                await asyncio.sleep(MESSAGE_TASK_INTERVAL)

        except asyncio.CancelledError:
            pass
        except Exception as ex:
            logger.error(f"Unhandled exception in handle loop: {ex}")

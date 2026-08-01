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
        state = load_state()
        self.message_id = state["message_id"] if state else None
        self.last_task = None
        self.last_img_hash = None
        self.has_media = False  # Track if current post is photo or text
        self.current_act = None

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

    def update_message_id(self, new_id: int | None, has_media: bool = False):
        self.message_id = new_id
        self.has_media = has_media if new_id else False
        save_state(self.chat_id, new_id)

    async def run_task(self, act: Activity):
        self.current_act = act

        # Start handle task if not running
        if self.last_task is None or self.last_task.done():
            if self.message_id is None:
                await self.cleanup_orphan()
            self.last_task = asyncio.create_task(self.handle())
            logger.trace("Message loop task started.")

    async def pause(self):
        if self.last_task:
            self.last_task.cancel()
            self.last_task = None
        try:
            if self.message_id:
                await telegram.delete_message(self.chat_id, self.message_id)
        except Exception as e:
            logger.trace(f"Pause delete exception ignored: {e}")
        finally:
            self.update_message_id(None)
            self.last_img_hash = None
            logger.trace("Message post deleted and loop stopped.")

    async def handle(self):
        try:
            while True:
                act = self.current_act
                if not act:
                    await asyncio.sleep(MESSAGE_TASK_INTERVAL)
                    continue

                try:
                    text_content = formatter.get_message_text(act)
                    small_url = act.assets.small_image_url if act.assets else None
                    small_hash = hashlib.md5(str(small_url).encode('utf-8')).hexdigest() if small_url else None
                    incoming_has_media = small_url is not None

                    # If transitioning between Photo Post <-> Text Post, delete old post first
                    if self.message_id and (self.has_media != incoming_has_media):
                        try:
                            await telegram.delete_message(self.chat_id, self.message_id)
                        except Exception:
                            pass
                        self.update_message_id(None)
                        self.last_img_hash = None

                    if self.message_id is None:
                        # Create a new post
                        if incoming_has_media:
                            new_id = await telegram.send_message(
                                self.chat_id, 
                                text_content, 
                                act.assets.get_small_image()
                            )
                            self.update_message_id(new_id, has_media=True)
                        else:
                            new_id = await telegram.send_message(self.chat_id, text_content)
                            self.update_message_id(new_id, has_media=False)
                        
                        self.last_img_hash = small_hash
                    else:
                        # Edit in-place when message type remains identical
                        if incoming_has_media:
                            if self.last_img_hash != small_hash:
                                # New cover image: edit photo + caption
                                await telegram.edit_media(
                                    self.chat_id, 
                                    self.message_id, 
                                    text_content, 
                                    act.assets.get_small_image()
                                )
                                self.last_img_hash = small_hash
                            else:
                                # Same cover: edit caption/timer only
                                await telegram.edit_media(self.chat_id, self.message_id, text_content)
                        else:
                            # Text-only edit (Game to Game)
                            await telegram.edit_text(self.chat_id, self.message_id, text_content)

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

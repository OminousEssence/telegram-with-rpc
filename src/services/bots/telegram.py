import os, asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BufferedInputFile, Message, InputMediaPhoto
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramServerError, TelegramNetworkError, TelegramAPIError
from loguru import logger
from colorama import Fore

dp = Dispatcher()
bot: Bot = None

async def init():
    global TOKEN, CHAT_ID, bot
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID'))
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

async def start():
    await bot.delete_webhook(drop_pending_updates=True)
    
    while True:
        try:
            await dp.start_polling(bot)
            break
        except (TelegramRetryAfter, TelegramServerError, TelegramNetworkError, Exception) as e:
            logger.warning(f"Telegram polling lost network ({e}). Reconnecting in 5s...")
            await asyncio.sleep(5)

@dp.startup()
async def startup():
    me = await bot.get_me()
    logger.info(f'@{me.username} is ready!')

# Helper to retry network operations automatically
async def safe_api_call(coro_func, *args, retries=5, delay=3, **kwargs):
    for attempt in range(retries):
        try:
            return await coro_func(*args, **kwargs)
        except (TelegramNetworkError, TelegramServerError) as e:
            logger.warning(f"Network error on attempt {attempt + 1}/{retries}: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except TelegramRetryAfter as e:
            logger.warning(f"Telegram rate limited. Retrying in {e.retry_after}s...")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            raise e
    raise Exception("Max network retries reached.")

# == channel ==
async def edit_title(chat_id: int, title: str):
    await safe_api_call(bot.set_chat_title, chat_id, title)
    logger.trace(f"Chat {Fore.WHITE}TITLE{Fore.CYAN} has changed.")

async def edit_photo(chat_id: int, large_image: BufferedInputFile):
    await safe_api_call(bot.set_chat_photo, chat_id, large_image)
    logger.trace(f"Chat {Fore.WHITE}AVATAR{Fore.CYAN} has changed.")

# == message ==
async def send_message(chat_id: int, text: str, media: BufferedInputFile = None) -> int:
    if media:
        ret_msg = await safe_api_call(bot.send_photo, chat_id, media, caption=text, disable_notification=True)
        logger.trace(f"Message {Fore.WHITE}WITH PHOTO{Fore.CYAN} has sent.")
    else:
        ret_msg = await safe_api_call(bot.send_message, chat_id, text, disable_notification=True)
        logger.trace(f"Message has sent.")
    return ret_msg.message_id

async def edit_media(chat_id: int, message_id: int, text: str, media: BufferedInputFile = None):
    if media:
        input_media = InputMediaPhoto(media=media, caption=text, parse_mode=ParseMode.HTML)
        await safe_api_call(bot.edit_message_media, input_media, chat_id=chat_id, message_id=message_id)
        logger.trace("PHOTO and CAPTION edited.")
    else:
        await safe_api_call(bot.edit_message_caption, chat_id=chat_id, message_id=message_id, caption=text, parse_mode=ParseMode.HTML)

async def edit_text(chat_id: int, message_id: int, text: str):
    await safe_api_call(bot.edit_message_text, chat_id=chat_id, message_id=message_id, text=text)

async def delete_message(chat_id: int, message_id: int):
    await safe_api_call(bot.delete_message, chat_id=chat_id, message_id=message_id)
    logger.trace(f"{Fore.RED}ACTIVITY{Fore.CYAN} post removed.")

# == auto clean channel system messages ==
@dp.channel_post()
async def channel_post(message: Message):
    triggers = [message.new_chat_photo, message.new_chat_title, message.delete_chat_photo]
    for t in triggers:
        if t:
            try:
                await safe_api_call(message.delete)
                logger.trace(f"{Fore.RED}CHANNEL{Fore.CYAN} post removed.")
            except Exception:
                pass
            break

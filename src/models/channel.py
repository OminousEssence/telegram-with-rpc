from models.activity import Activity
from services.bots import telegram
from config import ACTIVITY_TITLES, ACT_NONE_TITLE
from loguru import logger
from colorama import Fore
from utils import images
import hashlib
import discord

class Channel:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.last_avatar_hash = None
        self.last_title = None

    async def update(self, act: Activity):
        try:
            # 1. Update channel photo
            if act.assets and act.assets.large_image_url:
                url_str = str(act.assets.large_image_url)

                # Filter out generic Discord app fallback icons (/app-assets/)
                is_http = url_str.startswith("http://") or url_str.startswith("https://")
                is_app_logo = "app-assets" in url_str.lower()

                if is_http and not is_app_logo:
                    avatar_hash = hashlib.md5(url_str.encode('utf-8')).hexdigest()
                    if avatar_hash != self.last_avatar_hash:
                        photo = act.assets.get_large_image()
                        if photo:
                            await telegram.edit_photo(self.chat_id, photo)
                            self.last_avatar_hash = avatar_hash
                            logger.info(f"Channel {Fore.WHITE}PHOTO{Fore.BLUE} updated.")
                else:
                    logger.trace(f"Skipping channel photo update for app logo: {url_str}")
            else:
                # Reset to default empty avatar if no cover image is provided
                if self.last_avatar_hash is not None:
                    await telegram.edit_photo(self.chat_id, images.get_empty_avatar())
                    self.last_avatar_hash = None

            # 2. Update channel title
            if act.type == discord.ActivityType.playing:
                title = self.get_title_with_type_prefix(act)
            else:
                title = f"{self.get_title_with_type_prefix(act)} {act.name}"

            if title != self.last_title:
                await telegram.edit_title(self.chat_id, title)
                self.last_title = title
                logger.info(f"Channel {Fore.WHITE}TITLE{Fore.BLUE} updated.")
        except Exception as ex:
            logger.error(f"Channel update exception: {ex}")

    async def reset(self):
        try:
            await telegram.edit_title(self.chat_id, ACT_NONE_TITLE)
            await telegram.edit_photo(self.chat_id, images.get_empty_avatar())
        except Exception as ex:
            logger.error(f"Channel reset exception: {ex}")
        
        self.last_avatar_hash = None
        self.last_title = None

    def get_title_with_type_prefix(self, act: Activity):
        return ACTIVITY_TITLES.get(act.type, "⏱️")

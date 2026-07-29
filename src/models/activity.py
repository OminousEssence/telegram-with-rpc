from datetime import datetime
from config import SPOTIFY_LOGO_URL
import discord
import utils.images
import requests
import urllib.parse
from loguru import logger

GAME_ICON_CACHE = {}

def get_game_cover_url(game_name: str, app_id: int | str | None = None) -> str | None:
    if not game_name:
        return None
    
    if game_name in GAME_ICON_CACHE:
        return GAME_ICON_CACHE[game_name]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 1. Fetch Discord's official app icon using App ID directly
    if app_id:
        try:
            res = requests.get(f"https://discord.com/api/v10/applications/{app_id}/rpc", headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                icon_hash = data.get("icon")
                if icon_hash:
                    url = f"https://cdn.discordapp.com/app-icons/{app_id}/{icon_hash}.png?size=512"
                    logger.info(f"Resolved Clean Discord App Icon: {url}")
                    GAME_ICON_CACHE[game_name] = url
                    return url
        except Exception as e:
            logger.trace(f"Discord RPC lookup failed: {e}")

    # 2. Query SteamGridDB API for clean Square Grid artwork
    try:
        sgdb_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{urllib.parse.quote(game_name)}"
    except Exception:
        pass

    # 3. Fallback to Steam's clean community app icon
    if app_id:
        steam_icon_url = f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{app_id}/header.jpg"

    GAME_ICON_CACHE[game_name] = None
    return None


class ActivityAssets:
    def __init__(self, large_image_url, small_image_url):
        self.large_image_url = large_image_url
        self.small_image_url = small_image_url

    def get_large_image(self):
        if not self.large_image_url:
            return None
        return utils.images.ret_bif(self.large_image_url, True)

    def get_small_image(self):
        if not self.small_image_url:
            return None
        return utils.images.ret_bif(self.small_image_url)


class Activity:
    def __init__(self, act: discord.Activity | discord.Game | discord.Spotify):
        if isinstance(act, discord.Game):
            self.name = act.name
            app_id = getattr(act, 'application_id', None)
            
            large_url = getattr(act, 'large_image_url', None)
            if not large_url:
                large_url = get_game_cover_url(act.name, app_id)

            self.assets = ActivityAssets(large_url, getattr(act, 'small_image_url', None))
            self.type = getattr(act, 'type', discord.ActivityType.playing)
            self.start_time = getattr(act, 'start', None)
            self.end_time = getattr(act, 'end', None)

            if self.start_time and self.end_time:
                self.track_length = self.end_time - self.start_time
            else:
                self.track_length = None

            self.details = getattr(act, 'details', None) or act.name
            self.state = getattr(act, 'state', None)
            self.large_text = None
            self.large_url = None

        elif isinstance(act, discord.Activity):
            self.name = act.name
            large_url = getattr(act, 'large_image_url', None)
            app_id = getattr(act, 'application_id', None)
            
            if not large_url and act.type == discord.ActivityType.playing:
                large_url = get_game_cover_url(act.name, app_id)

            self.assets = ActivityAssets(large_url, getattr(act, 'small_image_url', None))
            self.type = act.type
            self.start_time = act.start
            self.end_time = act.end

            if self.start_time and self.end_time:
                self.track_length = self.end_time - self.start_time
            else:
                self.track_length = None

            self.details = act.details or act.name
            self.state = act.state
            
            assets_dict = getattr(act, 'assets', {}) or {}
            self.large_text = assets_dict.get("large_text", None) if isinstance(assets_dict, dict) else None
            self.large_url = assets_dict.get("large_url", None) if isinstance(assets_dict, dict) else None

        elif isinstance(act, discord.Spotify):
            self.name = "Spotify"
            self.assets = ActivityAssets(act.album_cover_url, SPOTIFY_LOGO_URL)
            self.type = discord.ActivityType.listening
            self.start_time = act.start
            self.end_time = act.end

            if self.start_time and self.end_time:
                self.track_length = self.end_time - self.start_time
            else:
                self.track_length = None

            self.details = act._details
            self.state = act._state
            self.large_text = None
            self.large_url = None

    def format_time(self, total_seconds: int) -> str:
        days = total_seconds // (24 * 3600)
        hours = (total_seconds % (24 * 3600)) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if days > 0:
            return f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
        elif hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

    def get_elapsed_time(self) -> str:
        if self.start_time is None:
            self.start_time = datetime.now()

        elapsed_time = datetime.now().timestamp() - self.start_time.timestamp()
        return self.format_time(max(0, int(elapsed_time)))

    def get_track_length(self) -> str:
        if self.track_length is None:
            return "00:00"
        total_seconds = self.track_length.total_seconds()
        return self.format_time(int(total_seconds))

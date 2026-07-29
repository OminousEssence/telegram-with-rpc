from aiogram.types import BufferedInputFile
from loguru import logger
from colorama import Fore
from config import MAX_ASSET_CACHE_SIZE
from PIL import Image, ImageOps, ImageEnhance
import requests, hashlib, sys, io
from utils.proxy import DISCORD_PROXY

cache = {}

def resize_img(image: Image, size: tuple = (1024, 1024)) -> Image:
    # 1. High-quality LANCZOS downsampling preserves fine details and sharpness
    resized = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.4))
    
    # 2. Subtle contrast & sharpness enhancement for dark/ambient game covers
    enhancer = ImageEnhance.Sharpness(resized)
    resized = enhancer.enhance(1.15)
    
    return resized

def create_bg(image: Image) -> Image:
    avg_color = get_avg_color(image)
    # Slightly richer ambient fill for padding
    darker_color = tuple(int(c * 0.45) for c in avg_color)
    background = Image.new("RGB", image.size, darker_color)
    return background

def get_avg_color(image: Image) -> tuple:
    image = image.convert("RGB")
    pixels = list(image.getdata())
    avg_r = sum([pixel[0] for pixel in pixels]) // len(pixels)
    avg_g = sum([pixel[1] for pixel in pixels]) // len(pixels)
    avg_b = sum([pixel[2] for pixel in pixels]) // len(pixels)
    return (avg_r, avg_g, avg_b)

def ret_bif(url: str, resize: bool = False) -> BufferedInputFile:
    if sys.getsizeof(cache) / 1024 >= MAX_ASSET_CACHE_SIZE:
        logger.debug("Clearing cache . . .")
        cache.clear()
    
    HASH = hashlib.md5(url.encode()).hexdigest()

    if HASH in cache and cache[HASH]['isResized'] == resize:
        logger.trace(f"Using cached image for: {Fore.WHITE}{url}")
        return cache[HASH]['file']
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    response = None
    if DISCORD_PROXY:
        try:
            response = requests.get(url, headers=headers, proxies={"http": DISCORD_PROXY, "https": DISCORD_PROXY}, timeout=5)
        except Exception:
            pass

    if response is None or response.status_code != 200:
        try:
            response = requests.get(url, headers=headers, timeout=5)
        except Exception as e:
            logger.error(f"Failed to download asset: {e}")
            return None

    if response.status_code != 200:
        logger.error(f"Failed to download asset {Fore.WHITE}[Code: {response.status_code}]")
        return None
    
    CONTENT = io.BytesIO(response.content)
    image = Image.open(CONTENT).convert("RGBA")

    if resize:
        image = resize_img(image)
    
    background = create_bg(image)
    background.paste(image, (0, 0), image)
    
    ret = io.BytesIO()
    # Save as full-quality PNG
    background.convert("RGB").save(ret, format="PNG", optimize=True)
    ret.seek(0)
    
    cache[HASH] = {'file': BufferedInputFile(ret.getvalue(), filename="rpc_asset.png"), 'isResized': resize}
    return cache[HASH]['file']

def get_empty_avatar() -> BufferedInputFile:
    avatar = Image.new("RGB", (1024, 1024), "#111111")
    ret = io.BytesIO()
    avatar.save(ret, format="PNG")
    ret.seek(0)
    return BufferedInputFile(ret.getvalue(), filename="empty.png")

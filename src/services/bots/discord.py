import discord
import asyncio
import os
import hashlib
from config import RPC_WATCHER_INTERVAL, SORT_ACTIVITIES
from loguru import logger
from services.events import events, RPC_UPDATED
from colorama import Fore
from models.activity import Activity
from utils.proxy import get_proxy

intents = discord.Intents.default()
intents.presences = True
intents.guilds = True
intents.members = True
intents.message_content = True

ALLOWED_TYPES = [discord.ActivityType.playing, discord.ActivityType.listening, discord.ActivityType.watching]
last_rpc_hash = None

ready_event = asyncio.Event()

async def init():
    global GUILD_ID, MEMBER_ID, RPC_WATCHER_INTERVAL, BOT_TOKEN, client

    # init env
    GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))
    MEMBER_ID = int(os.getenv('DISCORD_MEMBER_ID'))
    BOT_TOKEN = os.getenv('DISCORD_TOKEN')

    # init client
    ds_proxy = get_proxy()
    if not ds_proxy:
        client = discord.Client(intents=intents)
    else:
        logger.info("* Init with proxy.")
        client = discord.Client(intents=intents, proxy=ds_proxy)

    @client.event
    async def on_ready():
        logger.info(f'{client.user.name} is ready!')
        ready_event.set()

def get_valid_act(acts):
    if not acts:
        return None
    
    if SORT_ACTIVITIES:
        acts = sorted(acts, key=lambda act: (
            ALLOWED_TYPES.index(act.type) if act.type in ALLOWED_TYPES 
            else len(ALLOWED_TYPES)
        ))
    
    for act in acts:
        if act.type in ALLOWED_TYPES:
            return act
    
    return None

async def handle_act(act):    
    global last_rpc_hash
    
    if act is None:
        if last_rpc_hash is not None:
            last_rpc_hash = None
            await events.call(RPC_UPDATED, None)
        return
    
    ret_act = Activity(act)
    
    # Games (playing) bypass cover requirement, but non-games require artwork
    if act.type != discord.ActivityType.playing and ret_act.assets.large_image_url is None:
        if last_rpc_hash is not None:
            last_rpc_hash = None
            await events.call(RPC_UPDATED, None)
        return
    
    raw_data = getattr(act, 'to_dict', lambda: str(act))()
    rpc_hash = hashlib.md5(str(raw_data).encode('utf-8')).hexdigest()
    
    if rpc_hash != last_rpc_hash:
        last_rpc_hash = rpc_hash
        logger.debug(f"RPC Updated! [{ret_act.name} - {ret_act.details}]")
        await events.call(RPC_UPDATED, ret_act)

async def watcher_loop():
    await ready_event.wait()
    
    guild = client.get_guild(GUILD_ID)
    if guild is None:
        logger.error(f'Guild [ID: {GUILD_ID}] not found!')
        return
    
    while True:
        member = guild.get_member(MEMBER_ID)
        if member:
            act = get_valid_act(member.activities)
            await handle_act(act)
        else:
            logger.warning(f'Member [ID: {MEMBER_ID}] not found in cache.')

        await asyncio.sleep(RPC_WATCHER_INTERVAL / 1000)

async def start_client():
    await client.start(BOT_TOKEN)

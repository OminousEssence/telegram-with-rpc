import asyncio
import dotenv, os, sys
from loguru import logger

# Load environment variables early & set trace logging before imports
dotenv.load_dotenv()

if os.getenv('ENABLE_TRACE_LOGGING') == 'true':
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

from services.bots import discord
from services.bots import telegram
from models.channel import Channel
from models.activity import Activity
from models.message import Message
from services.events import events, RPC_UPDATED
from config import (
    MESSAGE_TASK_INTERVAL, 
    RPC_DEBOUNCE_INTERVAL, 
    IDLE_GRACE_PERIOD
)

if MESSAGE_TASK_INTERVAL < 5:
    logger.warning("The interval is too low. A timeout from Telegram is possible!")

grace_period_task: asyncio.Task | None = None
latest_activity: Activity | None = None # Cache latest state for recovery

async def discord_task():
    await discord.init()
    await asyncio.gather(
        discord.start_client(), # start bot
        discord.watcher_loop() # rpc watcher
    )

async def telegram_task():
    global channel, message
    await telegram.init()
    channel = Channel(telegram.CHAT_ID) # channel object
    message = Message(telegram.CHAT_ID) # message object
    
    # Start polling and auto-resync if connection resets
    while True:
        try:
            await telegram.start()
        except Exception as e:
            logger.error(f"Telegram task disconnected: {e}. Reconnecting...")
            await asyncio.sleep(5)
            # Re-trigger state sync once reconnected
            if latest_activity is not None:
                await channel.update(latest_activity)
                await message.run_task(latest_activity)

async def clear_idle_state():
    # Triggers only if the activity remains None/Closed for the full grace period.
    global latest_activity, grace_period_task
    try:
        await asyncio.sleep(IDLE_GRACE_PERIOD)
        logger.info(f"Idle grace period ({IDLE_GRACE_PERIOD}s) expired. Cleaning up channel & post.")
        latest_activity = None
        await message.pause()
        try:
            await channel.reset()
        except Exception as e:
            logger.warning(f"Failed to reset channel title: {e}")
    except asyncio.CancelledError:
        logger.trace("Grace period cancelled — Activity resumed!")
    finally:
        grace_period_task = None

@events.on_call(RPC_UPDATED)
async def on_call(act: Activity):
    global grace_period_task, latest_activity

    # 1. Playback paused or stopped
    if act is None:
        # If there is active post running and no timer is counting down, start grace period
        if latest_activity is not None and grace_period_task is None:
            logger.debug(f"Activity dropped to None. Waiting {IDLE_GRACE_PERIOD}s before deleting post...")
            grace_period_task = asyncio.create_task(clear_idle_state())
        return

    # 2. Activity resumed or switched
    if grace_period_task:
        grace_period_task.cancel()
        grace_period_task = None
        logger.debug("Activity resumed. Cancelled idle grace period.")

    latest_activity = act
    
    # Update channel info (channel.py checks internally if title/photo actually changed)
    try:
        await channel.update(act)
    except Exception as e:
        logger.warning(f"Failed to update channel title: {e}")

    # Pass activity to message handler
    await message.run_task(act)

async def main():
    tasks = [
        discord_task(),
        telegram_task()
    ]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())

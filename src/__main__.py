import asyncio
import dotenv, os, sys
from loguru import logger

# 1. Load environment variables early & set trace logging before imports
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
from config import MESSAGE_TASK_INTERVAL, RPC_DEBOUNCE_INTERVAL

if MESSAGE_TASK_INTERVAL < 5:
    logger.warning("The interval is too low. A timeout from Telegram is possible!")

pending_update_task: asyncio.Task | None = None
latest_activity: Activity | None = None  # Cache latest state for recovery

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
                asyncio.create_task(debounced_rpc_update(latest_activity))

@events.on_call(RPC_UPDATED)
async def on_call(act: Activity):
    global pending_update_task, latest_activity
    latest_activity = act  # Save current state

    if pending_update_task and not pending_update_task.done():
        pending_update_task.cancel()
        logger.trace("Rapid activity event detected. Resetting debounce timer...")

    pending_update_task = asyncio.create_task(debounced_rpc_update(act))

async def debounced_rpc_update(act: Activity):
    try:
        await asyncio.sleep(RPC_DEBOUNCE_INTERVAL)

        if act is None:
            await channel.reset()
            await message.pause()
        else:
            await channel.update(act)
            await message.run_task(act)

    except asyncio.CancelledError:
        pass
    except Exception as ex:
        logger.error(f"Error executing debounced RPC update: {ex}")

async def main():
    tasks = [
        discord_task(),
        telegram_task()
    ]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())

from hydrogram import Client
from logging import getLogger
from itertools import cycle
from importlib import import_module
import pkgutil

from bot.config import Telegram, validate_configuration
from bot.database import db

logger = getLogger('bot')

# Bot sessions are intentionally in-memory. Bots already authenticate with their
# BotFather tokens on every start, so persisting Hydrogram SQLite session files
# provides little benefit and can become corrupted when a process is interrupted
# or two deployments accidentally overlap.
TelegramBot = Client(
    name='bot_main',
    api_id=Telegram.API_ID,
    api_hash=Telegram.API_HASH,
    bot_token=Telegram.BOT_TOKEN,
    in_memory=True,
    sleep_threshold=-1,
    max_concurrent_transmissions=10,
    ipv6=False
)

# Multi-Client Worker Pool (Used for fast parallel chunk downloading and streaming)
worker_clients: list[Client] = []
_worker_cycler = None
_plugins_loaded = False

LAST_HEARTBEAT_TIME = 0.0
HEARTBEAT_PINGS_COUNT = 0


def record_heartbeat_ping():
    global LAST_HEARTBEAT_TIME, HEARTBEAT_PINGS_COUNT
    import time
    LAST_HEARTBEAT_TIME = time.time()
    HEARTBEAT_PINGS_COUNT += 1


def get_heartbeat_status() -> tuple[int, float]:
    return HEARTBEAT_PINGS_COUNT, LAST_HEARTBEAT_TIME


def load_bot_plugins():
    """Import every module in bot.plugins exactly once."""
    global _plugins_loaded
    if _plugins_loaded:
        return

    package = import_module('bot.plugins')
    modules = sorted(
        pkgutil.iter_modules(package.__path__, package.__name__ + '.'),
        key=lambda item: item.name,
    )
    loaded = 0
    for module_info in modules:
        import_module(module_info.name)
        loaded += 1

    _plugins_loaded = True
    logger.info("Loaded %d bot plugin module(s).", loaded)


def init_worker_clients():
    global worker_clients, _worker_cycler
    worker_clients.clear()

    # 1. The primary TelegramBot is worker #0 (reuse existing connection).
    worker_clients.append(TelegramBot)

    # 2. Add de-duplicated extra worker bots.
    for idx, token in enumerate(Telegram.WORKER_TOKENS[1:], start=1):
        worker = Client(
            name=f'worker_{idx}',
            api_id=Telegram.API_ID,
            api_hash=Telegram.API_HASH,
            bot_token=token,
            in_memory=True,
            sleep_threshold=-1,
            max_concurrent_transmissions=10,
            no_updates=True,
            ipv6=False
        )
        worker_clients.append(worker)

    _worker_cycler = cycle(worker_clients)
    logger.info("Initialized %d bot client(s) in worker pool.", len(worker_clients))


def get_worker_client() -> Client:
    global _worker_cycler
    if not worker_clients:
        return TelegramBot
    if _worker_cycler is None:
        _worker_cycler = cycle(worker_clients)
    return next(_worker_cycler)


async def start_all_clients():
    import os
    import time

    validate_configuration()
    load_bot_plugins()

    # Connect MongoDB
    await db.connect()

    # Start Main Bot
    logger.info("Starting Main Telegram Bot...")
    try:
        await TelegramBot.start()
    except Exception:
        db.close()
        raise
    await db.create_indexes()

    # Check and resolve pending restart notification
    if os.path.exists('.restart_state.txt'):
        try:
            with open('.restart_state.txt', 'r') as f:
                parts = f.read().strip().split()
            if len(parts) >= 2:
                chat_id = int(parts[0])
                msg_id = int(parts[1])
                duration_str = ""
                if len(parts) >= 3:
                    elapsed = round(time.time() - float(parts[2]), 1)
                    duration_str = f" in `{elapsed}s`"
                await TelegramBot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        f"✅ **OmniArchiver Bot rebooted successfully{duration_str}!**\n\n"
                        f"🚀 Telegram and MongoDB are connected. Worker and web services are starting."
                    )
                )
        except Exception as e:
            logger.warning("Failed to edit restart notification: %s", e)
        finally:
            try:
                os.remove('.restart_state.txt')
            except Exception:
                pass

    # Start Worker Clients
    init_worker_clients()
    logger.info("Starting Worker Clients pool (%d total)...", len(worker_clients))
    for idx, client in enumerate(worker_clients):
        if client == TelegramBot:
            continue
        try:
            await client.start()
            logger.info("Worker client #%d started successfully.", idx)
        except Exception as e:
            logger.warning("Failed to start worker client #%d: %s", idx, e)

    # Do not keep failed clients in the round-robin pool.
    active_clients = [TelegramBot]
    for idx, client in enumerate(list(worker_clients)[1:], start=1):
        if getattr(client, 'is_connected', False):
            active_clients.append(client)
        else:
            logger.warning("Worker client #%d excluded from the active pool.", idx)
    worker_clients[:] = active_clients
    global _worker_cycler
    _worker_cycler = cycle(worker_clients)


async def stop_all_clients():
    logger.info("Stopping all clients...")
    for client in worker_clients:
        if client == TelegramBot:
            continue
        try:
            if client.is_connected:
                await client.stop()
        except Exception:
            pass
    if TelegramBot.is_connected:
        await TelegramBot.stop()
    db.close()
    logger.info("All clients stopped.")

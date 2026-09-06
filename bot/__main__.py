import asyncio
from hydrogram import idle
from bot.clients import (
    start_all_clients,
    stop_all_clients,
    TelegramBot,
    worker_clients,
    record_heartbeat_ping
)
from bot.server import server
from bot.modules.memory import flush_ram

from logging import getLogger
logger = getLogger('heartbeat')

async def keep_alive_heartbeat():
    """Keeps all Telegram MTProto worker sockets warm, auto-reconnects dead sockets, and compacts RAM every 2 minutes."""
    # Short initial delay on boot
    await asyncio.sleep(5)
    while True:
        try:
            active_pings = 0
            for client in list(worker_clients):
                if client:
                    try:
                        if not getattr(client, 'is_connected', False):
                            await client.connect()
                        await client.get_me()
                        active_pings += 1
                    except Exception:
                        try:
                            # Re-establish dead connection socket
                            await client.connect()
                            await client.get_me()
                            active_pings += 1
                        except Exception:
                            pass
            record_heartbeat_ping()
            logger.info("💓 Telegram DC heartbeat sent across %d worker(s).", active_pings)
            # Auto-compact RAM
            flush_ram()
            await asyncio.sleep(120)  # Every 2 minutes
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(10)

async def main():
    await start_all_clients()
    server_task = asyncio.create_task(server.serve(), name="web-server")
    heartbeat_task = asyncio.create_task(keep_alive_heartbeat(), name="telegram-heartbeat")
    idle_task = asyncio.create_task(idle(), name="telegram-idle")

    try:
        done, _ = await asyncio.wait(
            {idle_task, server_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If the web server stopped unexpectedly, surface its exception instead
        # of leaving the Telegram bot apparently alive with dead HTTP links.
        if server_task in done and not server.should_exit:
            exc = server_task.exception()
            if exc:
                raise exc
            raise RuntimeError("Web server stopped unexpectedly.")
    finally:
        server.should_exit = True
        for task in (idle_task, heartbeat_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(idle_task, heartbeat_task, return_exceptions=True)

        if not server_task.done():
            try:
                await asyncio.wait_for(server_task, timeout=10)
            except asyncio.TimeoutError:
                server_task.cancel()
                await asyncio.gather(server_task, return_exceptions=True)

        await stop_all_clients()

if __name__ == '__main__':
    TelegramBot.loop.run_until_complete(main())

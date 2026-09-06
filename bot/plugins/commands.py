import os
import time
import shutil
import psutil
from datetime import timedelta
from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot, worker_clients
from bot.config import Telegram
from bot.database.files import get_stats, get_bandwidth_stats
from bot.modules.static import WelcomeText, PrivacyText, get_human_size
from bot.modules.decorators import verify_user, verify_admin

BOT_START_TIME = time.time()

def get_readable_time(seconds: int) -> str:
    result = []
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    
    if days > 0:
        result.append(f"{days}d")
    if hours > 0:
        result.append(f"{hours}h")
    if minutes > 0:
        result.append(f"{minutes}m")
    result.append(f"{seconds}s")
    
    return " ".join(result)

@TelegramBot.on_message(filters.command(['start', 'help']) & filters.private)
@verify_user
async def start_command(_, msg: Message):
    await msg.reply(
        text=WelcomeText % {'first_name': msg.from_user.first_name},
        quote=True,
        disable_web_page_preview=True
    )

@TelegramBot.on_message(filters.command('privacy') & filters.private)
@verify_user
async def privacy_command(_, msg: Message):
    await msg.reply(text=PrivacyText, quote=True, disable_web_page_preview=True)

@TelegramBot.on_message(filters.command('stats') & filters.private)
@verify_user
@verify_admin
async def stats_command(_, msg: Message):
    # Database counts
    stats = await get_stats()
    total_files = sum(stats.values())
    
    # Bandwidth & Request analytics from MongoDB
    bytes_streamed, requests_count = await get_bandwidth_stats()
    bandwidth_str = get_human_size(bytes_streamed)

    # Uptime
    uptime = get_readable_time(int(time.time() - BOT_START_TIME))

    # Process RAM & CPU
    try:
        process = psutil.Process(os.getpid())
        bot_ram = get_human_size(process.memory_info().rss)
    except Exception:
        bot_ram = "N/A"

    try:
        sys_ram = psutil.virtual_memory()
        sys_ram_str = f"{get_human_size(sys_ram.used)} / {get_human_size(sys_ram.total)} ({sys_ram.percent}%)"
    except Exception:
        sys_ram_str = "N/A"

    try:
        cpu_usage = f"{psutil.cpu_percent(interval=0.1)}%"
    except Exception:
        cpu_usage = "N/A"

    # Actual Bot Project Disk Space vs Shared Host Node Storage
    try:
        bot_disk_bytes = 0
        for root, dirs, files in os.walk('.'):
            if '.git' in dirs:
                dirs.remove('.git')
            for f in files:
                fp = os.path.join(root, f)
                try:
                    bot_disk_bytes += os.path.getsize(fp)
                except OSError:
                    pass
        bot_disk_str = get_human_size(bot_disk_bytes)
    except Exception:
        bot_disk_str = "N/A"

    try:
        disk = shutil.disk_usage('.')
        disk_pct = round((disk.used / disk.total) * 100, 1)
        host_disk_str = f"{get_human_size(disk.used)} / {get_human_size(disk.total)} ({disk_pct}%)"
    except Exception:
        host_disk_str = "N/A"

    # 24/7 Heartbeat status
    try:
        from bot.clients import get_heartbeat_status
        pings_count, last_time = get_heartbeat_status()
        if last_time > 0:
            elapsed = max(0, int(time.time() - last_time))
            heartbeat_str = f"Active ({pings_count} pings • {elapsed}s ago)"
        else:
            heartbeat_str = "Active (Starting up...)"
    except Exception:
        heartbeat_str = "Active"

    text = (
        "📊 **OmniArchiver Live System & Database Stats**\n\n"
        f"🎬 **Movies Indexed:** `{stats.get('movies', 0)}`\n"
        f"📺 **Anime Episodes:** `{stats.get('anime', 0)}`\n"
        f"🍿 **Web Series:** `{stats.get('webseries', 0)}`\n"
        f"📁 **Direct Files:** `{stats.get('direct_files', 0)}`\n"
        f"📦 **Total Files:** `{total_files}`\n"
        f"{'─'*28}\n"
        f"🤖 **Active Worker Bots:** `{len(worker_clients)}`\n"
        f"👑 **Admins Registered:** `{len(Telegram.ADMIN_IDS)}`\n"
        f"⏱️ **System Uptime:** `{uptime}`\n"
        f"💓 **24/7 Heartbeat:** `{heartbeat_str}`\n"
        f"{'─'*28}\n"
        f"🧠 **Bot Process RAM:** `{bot_ram}`\n"
        f"💾 **Bot Project Disk:** `{bot_disk_str}`\n"
        f"💻 **Host Node RAM:** `{sys_ram_str}`\n"
        f"🖥️ **Host Node Disk (Shared):** `{host_disk_str}`\n"
        f"⚡ **CPU Usage:** `{cpu_usage}`\n"
        f"🌐 **Total Bandwidth Streamed:** `{bandwidth_str}` (`{requests_count} hits`)\n"
    )
    await msg.reply(text, quote=True)

@TelegramBot.on_message(filters.command('log') & filters.private)
@verify_user
@verify_admin
async def log_command(_, msg: Message):
    try:
        await msg.reply_document('event-log.txt', quote=True)
    except Exception as e:
        await msg.reply(f"❌ Failed to send log file: `{e}`", quote=True)

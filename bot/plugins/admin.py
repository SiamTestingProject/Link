import os
import sys
import io
import asyncio
import signal
from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot
from bot.modules.decorators import verify_user, verify_admin

@TelegramBot.on_message(filters.command(['sh', 'shell', 'exec']) & filters.private)
@verify_user
@verify_admin
async def shell_command(_, msg: Message):
    """Executes a terminal shell command directly from Telegram and returns the output."""
    if len(msg.command) < 2:
        return await msg.reply(
            "💻 **Shell Terminal Command**\n\n"
            "**Usage:**\n"
            "• `/sh git pull origin main`\n"
            "• `/sh pip install -r requirements.txt`\n"
            "• `/sh ls -la`",
            quote=True
        )

    cmd = msg.text.split(maxsplit=1)[1]
    status_msg = await msg.reply(f"⏳ **Executing:** `{cmd}`", quote=True)

    try:
        process_kwargs = {
            'stdout': asyncio.subprocess.PIPE,
            'stderr': asyncio.subprocess.PIPE,
        }
        if os.name == 'posix':
            # Put the shell and its children in their own process group so a
            # timeout can terminate the whole command tree, not only the shell.
            process_kwargs['start_new_session'] = True

        process = await asyncio.create_subprocess_shell(cmd, **process_kwargs)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            if process.returncode is None:
                try:
                    if os.name == 'posix':
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    try:
                        if os.name == 'posix':
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()
            return await status_msg.edit_text("❌ **Execution Timed Out** (limit: 120 seconds). Process terminated.")

        output = (stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')).strip()

        if not output:
            output = f"Command finished with exit code {process.returncode} (no output)."
        elif process.returncode:
            output = f"[exit code: {process.returncode}]\n{output}"

        if len(output) > 3800:
            file_bytes = io.BytesIO(output.encode('utf-8'))
            file_bytes.name = "output.txt"
            await status_msg.delete()
            await msg.reply_document(
                document=file_bytes,
                caption=f"📄 **Output for:** `{cmd[:60]}`",
                quote=True
            )
        else:
            await status_msg.edit_text(f"💻 **Output:**\n```bash\n{output}\n```")

    except Exception as e:
        await status_msg.edit_text(f"❌ **Error executing command:** `{e}`")

@TelegramBot.on_message(filters.command(['restart', 'reboot']) & filters.private)
@verify_user
@verify_admin
async def restart_command(_, msg: Message):
    """Restarts the bot process smoothly and notifies user upon coming back online."""
    import time
    restart_msg = await msg.reply("🔄 **Restarting OmniArchiver Bot...**\nPlease wait ~5-10 seconds.", quote=True)

    # Save state to edit message after reboot
    try:
        with open('.restart_state.txt', 'w') as f:
            f.write(f"{msg.chat.id} {restart_msg.id} {time.time()}")
    except Exception:
        pass

    # Touch start.sh to notify Alwaysdata supervisor if applicable
    try:
        if os.path.exists("start.sh"):
            os.utime("start.sh", None)
    except Exception:
        pass

    await asyncio.sleep(1.5)

    # Replace current python process
    os.execl(sys.executable, sys.executable, "-m", "bot")

@TelegramBot.on_message(filters.command(['purge', 'clear']) & filters.private)
@verify_user
@verify_admin
async def purge_command(client, msg: Message):
    """Purges messages from the chat."""
    if msg.reply_to_message:
        start_id = msg.reply_to_message.id
        end_id = msg.id
        message_ids = list(range(start_id, end_id + 1))
        
        # Batch delete messages
        for i in range(0, len(message_ids), 100):
            chunk = message_ids[i:i + 100]
            try:
                await client.delete_messages(chat_id=msg.chat.id, message_ids=chunk)
            except Exception:
                pass
                
        status = await client.send_message(
            chat_id=msg.chat.id,
            text=f"🧹 **Purged {len(message_ids)} messages successfully!**"
        )
        await asyncio.sleep(3)
        await status.delete()

    elif len(msg.command) > 1 and msg.command[1].isdigit():
        count = max(1, min(int(msg.command[1]), 100))
        start_id = max(1, msg.id - count + 1)
        message_ids = list(range(start_id, msg.id + 1))
        
        try:
            await client.delete_messages(chat_id=msg.chat.id, message_ids=message_ids)
        except Exception:
            pass
            
        status = await client.send_message(
            chat_id=msg.chat.id,
            text=f"🧹 **Purged last {len(message_ids)} messages!**"
        )
        await asyncio.sleep(3)
        await status.delete()
        
    else:
        await msg.reply(
            "🧹 **Purge Usage:**\n"
            "• Reply to a message with `/purge` to delete everything from that message downwards.\n"
            "• Send `/purge 20` to delete the last 20 messages.",
            quote=True
        )

@TelegramBot.on_message(filters.command(['clean', 'gc', 'flush']) & filters.private)
@verify_user
@verify_admin
async def clean_memory_command(_, msg: Message):
    """Manually cleans memory, runs cyclic garbage collection and releases freed heap back to OS."""
    import psutil
    from bot.modules.memory import flush_ram
    from bot.modules.static import get_human_size

    before_ram = psutil.Process(os.getpid()).memory_info().rss
    flush_ram()
    after_ram = psutil.Process(os.getpid()).memory_info().rss

    freed = before_ram - after_ram
    freed_str = get_human_size(max(0, freed))
    current_str = get_human_size(after_ram)

    await msg.reply(
        f"🧹 **RAM Cleaned & Compaction Finished!**\n\n"
        f"📉 **Freed Memory:** `{freed_str}`\n"
        f"🧠 **Current Bot Process RAM:** `{current_str}`",
        quote=True
    )

@TelegramBot.on_message(filters.command(['sync_duration', 'backfill', 'sync_metadata']) & filters.private)
@verify_user
@verify_admin
async def sync_duration_command(_, msg: Message):
    """Automatically scans all existing files/batches in MongoDB and backfills exact duration."""
    from bot.database import db
    from bot.modules.telegram import get_message, get_file_properties

    status = await msg.reply("⏳ **Syncing duration for all existing database records...**\nPlease wait...", quote=True)
    synced_files = 0
    synced_batches = 0

    try:
        # 1. Sync movies and direct files
        for col in (db.movies, db.direct_files):
            if col is not None:
                async for doc in col.find({'duration': {'$in': [None, 0, '']}}):
                    chan_id = doc.get('channel_id')
                    msg_id = doc.get('message_id')
                    if chan_id and msg_id:
                        try:
                            t_msg = await get_message(chan_id, msg_id)
                            if t_msg:
                                _, _, _, dur, dur_fmt = get_file_properties(t_msg)
                                await col.update_one(
                                    {'_id': doc['_id']},
                                    {'$set': {'duration': dur, 'duration_formatted': dur_fmt}}
                                )
                                synced_files += 1
                        except Exception:
                            pass
                    await asyncio.sleep(0.1)

        # 2. Sync anime and webseries batches
        for col in (db.anime, db.webseries):
            if col is not None:
                async for batch_doc in col.find():
                    chan_id = batch_doc.get('channel_id')
                    episodes = batch_doc.get('episodes', [])
                    updated = False

                    for ep in episodes:
                        if not ep.get('duration'):
                            msg_id = ep.get('message_id')
                            if chan_id and msg_id:
                                try:
                                    t_msg = await get_message(chan_id, msg_id)
                                    if t_msg:
                                        _, _, _, dur, dur_fmt = get_file_properties(t_msg)
                                        ep['duration'] = dur
                                        ep['duration_formatted'] = dur_fmt
                                        updated = True
                                        synced_files += 1
                                except Exception:
                                    pass
                                await asyncio.sleep(0.1)

                    if updated:
                        await col.update_one(
                            {'_id': batch_doc['_id']},
                            {'$set': {'episodes': episodes}}
                        )
                        synced_batches += 1

        await status.edit_text(
            f"✅ **Duration Backfill Completed Successfully!**\n\n"
            f"🎬 **Total Episodes/Files Updated:** `{synced_files}`\n"
            f"📁 **Batches Updated:** `{synced_batches}`\n\n"
            f"All your existing MongoDB records and REST API endpoints now include exact durations! ⏱️"
        )
    except Exception as e:
        await status.edit_text(f"❌ Error during sync: `{e}`")

@TelegramBot.on_message(filters.command(['revoke', 'del', 'delete_link', 'rm']) & filters.private)
@verify_user
@verify_admin
async def revoke_command(_, msg: Message):
    """Revokes an existing file link or batch from MongoDB so it can be re-indexed cleanly."""
    from bot.database.files import get_record, delete_file

    if len(msg.command) < 2:
        return await msg.reply(
            "🗑️ **Revoke / Delete Link Command**\n\n"
            "**Usage:**\n"
            "• `/revoke <file_code>`\n"
            "• `/revoke https://streamhub69.alwaysdata.net/dl/<file_code>`\n"
            "• `/revoke https://streamhub69.alwaysdata.net/stream/<file_code>`\n"
            "• `/revoke https://streamhub69.alwaysdata.net/api/file/<file_code>`\n\n"
            "*(You can also simply click the `[🗑️ Revoke]` button under any link card)*",
            quote=True
        )

    raw_input = msg.command[1].strip()
    # Extract code/id from URL if full URL is pasted
    code = raw_input.rstrip('/').split('/')[-1].strip()

    doc = await get_record(code)
    if not doc:
        return await msg.reply("❌ File link not found in database or was already revoked.", quote=True)

    file_title = doc.get('title') or doc.get('file_name', 'N/A')
    await delete_file(code)

    if doc.get('episodes') is not None:
        regenerate_hint = "Re-run the original `/batch anime ...` or `/batch series ...` command to index it again."
    else:
        regenerate_hint = "You can now generate a fresh link using `/link <channel_post_url>`."

    await msg.reply(
        f"🗑️ **Link Revoked Successfully!**\n\n"
        f"🎬 **Title:** `{file_title}`\n"
        f"🔑 **Code:** `{code}`\n\n"
        f"✨ The old database record has been cleared. {regenerate_hint}",
        quote=True
    )


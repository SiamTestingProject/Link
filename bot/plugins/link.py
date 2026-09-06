from hydrogram import filters
from hydrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.clients import TelegramBot
from bot.config import Server
from bot.database.files import save_file
from bot.modules.decorators import verify_user, verify_admin
from bot.modules.parser import parse_telegram_link
from bot.modules.telegram import get_message, get_file_properties, is_media_message
from bot.modules.static import MediaLinksText, FileLinksText, InvalidLinkText, get_human_size

@TelegramBot.on_message(filters.command(['link', 'movie']) & filters.private)
@verify_user
@verify_admin
async def link_command(_, msg: Message):
    # Check if a link was provided in command arguments
    channel_id = None
    message_id = None
    
    if len(msg.command) > 1:
        raw_link = msg.command[1]
        parsed = parse_telegram_link(raw_link)
        if not parsed:
            return await msg.reply(InvalidLinkText, quote=True)
        channel_id, message_id = parsed
    elif msg.reply_to_message:
        reply = msg.reply_to_message
        if reply.forward_from_chat and reply.forward_from_message_id:
            channel_id = reply.forward_from_chat.id
            message_id = reply.forward_from_message_id
        elif is_media_message(reply):
            # Direct media message replied to
            return await msg.reply("⚠️ Please forward the message from your channel or provide the post link:\n`/link <post_link>`", quote=True)
        else:
            return await msg.reply(InvalidLinkText, quote=True)
    else:
        return await msg.reply(
            "🎬 **Usage:**\n`/link https://t.me/c/1234567890/42`\n*(Or reply to any forwarded channel post with `/link`)*",
            quote=True
        )

    status_msg = await msg.reply("⏳ *Fetching message from channel and indexing...*", quote=True)
    
    try:
        target_msg = await get_message(channel_id, message_id)
        if not target_msg or not is_media_message(target_msg):
            return await status_msg.edit_text("❌ Could not find a valid media file in that channel message.\nMake sure the bot is an **Admin** in that channel!")

        file_name, file_size, mime_type, duration, duration_formatted = get_file_properties(target_msg)
        numeric_chat_id = target_msg.chat.id if target_msg.chat else channel_id
        
        # Save permanently to MongoDB 'movies' collection
        doc = await save_file(
            channel_id=numeric_chat_id,
            message_id=message_id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            user_id=msg.from_user.id,
            category='movies',
            duration=duration,
            duration_formatted=duration_formatted
        )
        
        code = doc['code']
        human_size = get_human_size(file_size)
        dl_link = f"{Server.BASE_URL}/dl/{code}"
        stream_link = f"{Server.BASE_URL}/stream/{code}"
        api_link = f"{Server.BASE_URL}/api/file/{code}"
        is_streamable = (mime_type or '').lower().startswith(('video/', 'audio/'))
        
        action_row = [InlineKeyboardButton('📥 Download', url=dl_link)]
        if is_streamable:
            action_row.append(InlineKeyboardButton('▶️ Stream', url=stream_link))
        buttons = [action_row, [InlineKeyboardButton('🗑️ Revoke', callback_data=f"rm_{code}")]]
        
        if is_streamable:
            caption = MediaLinksText % {
                'file_name': file_name,
                'file_size': human_size,
                'duration': duration_formatted,
                'category': 'Movies / Single File',
                'dl_link': dl_link,
                'stream_link': stream_link
            }
        else:
            caption = FileLinksText % {
                'file_name': file_name,
                'file_size': human_size,
                'duration': duration_formatted,
                'category': 'Single File',
                'dl_link': dl_link,
            }
        caption += f"\n⚡ **API:** `{api_link}`"
        
        await status_msg.edit_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error processing link: `{e}`")

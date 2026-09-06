from hydrogram import Client
from hydrogram.types import Message
from datetime import datetime
from mimetypes import guess_type
from bot.clients import TelegramBot, get_worker_client

async def get_message(
    chat_id: int | str,
    message_id: int,
    client: Client = None,
    raise_on_error: bool = False,
) -> Message | None:
    message = None
    target_client = client or get_worker_client() or TelegramBot
    last_error = None
    
    try:
        message = await target_client.get_messages(chat_id=chat_id, message_ids=message_id)
        if message and message.empty:
            message = None
    except Exception as exc:
        last_error = exc
        # Fallback to main TelegramBot if worker client fails
        if target_client != TelegramBot:
            try:
                message = await TelegramBot.get_messages(chat_id=chat_id, message_ids=message_id)
                if message and message.empty:
                    message = None
            except Exception as fallback_exc:
                last_error = fallback_exc
                message = None

    if message is None and raise_on_error and last_error is not None:
        raise last_error

    return message

def is_media_message(msg: Message) -> bool:
    if not msg:
        return False
    attributes = ('document', 'video', 'audio', 'voice', 'photo', 'video_note')
    return any(getattr(msg, attr, None) is not None for attr in attributes)

from bot.modules.static import format_duration

def get_file_properties(msg: Message) -> tuple[str, int, str, int, str]:
    if not msg:
        return None, 0, 'application/octet-stream', 0, 'N/A'
        
    attributes = (
        'video',
        'document',
        'audio',
        'voice',
        'photo',
        'video_note'
    )
    media = None
    file_type = None
    for attribute in attributes:
        media = getattr(msg, attribute, None)
        if media:
            file_type = attribute
            break

    if not media:
        return None, 0, 'application/octet-stream', 0, 'N/A'

    file_name = getattr(media, 'file_name', None)
    file_size = getattr(media, 'file_size', 0) or 0
    duration = getattr(media, 'duration', 0) or 0

    # If document, inspect attributes for video/audio duration
    if file_type == 'document' and not duration:
        for attr in getattr(media, 'attributes', []):
            if hasattr(attr, 'duration') and attr.duration:
                duration = attr.duration
                break

    # Extract clean file_name:
    # 1. Prefer message caption if it contains the episode/movie title as written in channel
    if msg.caption:
        first_line = msg.caption.strip().split('\n')[0].strip()
        if 3 < len(first_line) < 200:
            file_name = first_line
        else:
            file_name = getattr(media, 'file_name', None)
    else:
        file_name = getattr(media, 'file_name', None)

    # 2. Fallback to timestamp if neither caption nor media.file_name exists
    if not file_name:
        file_format = {
            'video': 'mp4',
            'audio': 'mp3',
            'voice': 'ogg',
            'photo': 'jpg',
            'video_note': 'mp4'
        }.get(file_type, 'bin')
        date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f'{file_type}-{date}.{file_format}'
    
    mime_type = getattr(media, 'mime_type', None)
    if not mime_type:
        mime_type = guess_type(file_name)[0] or 'application/octet-stream'

    duration_formatted = format_duration(duration)

    return file_name, file_size, mime_type, duration, duration_formatted

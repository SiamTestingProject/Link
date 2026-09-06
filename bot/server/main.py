import asyncio
from logging import getLogger
from urllib.parse import quote
from quart import Blueprint, Response, request, render_template, redirect, jsonify
from math import ceil
from re import fullmatch as re_fullmatch
from .error import abort
from bot.clients import get_worker_client, TelegramBot
from bot.config import Telegram, Server
from bot.database import db
from bot.database.files import get_file, add_bandwidth_bytes
from bot.modules.telegram import get_file_properties
from bot.modules.static import get_human_size
from bot.modules.memory import flush_ram

bp = Blueprint('main', __name__)
logger = getLogger('bot')


def _safe_download_name(file_name: str | None) -> str:
    """Keep user-controlled names from breaking HTTP response headers."""
    raw_name = str(file_name or 'download.bin')
    # Strip HTTP control characters and header delimiters from user-controlled
    # Telegram captions/file names before constructing Content-Disposition.
    name = ''.join('_' if ord(ch) < 32 or ord(ch) == 127 else ch for ch in raw_name)
    name = name.replace('\\', '_').replace('"', "'")
    return name[:240] or 'download.bin'


def _content_disposition(file_name: str | None, disposition: str = 'attachment') -> str:
    """Build an RFC 5987-compatible attachment header for Unicode filenames."""
    if disposition not in ('attachment', 'inline'):
        disposition = 'attachment'
    safe_name = _safe_download_name(file_name)
    ascii_fallback = safe_name.encode('ascii', errors='replace').decode('ascii').replace('?', '_')
    encoded = quote(safe_name, safe='')
    return f'{disposition}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def _parse_byte_range(range_header: str | None, file_size: int) -> tuple[int, int, bool]:
    """Parse a single RFC 7233 byte range and clamp it to the file size."""
    def unsatisfiable(description='Requested range not satisfiable'):
        abort(
            416,
            description,
            headers={
                'Content-Range': f'bytes */{max(file_size, 0)}',
                'Accept-Ranges': 'bytes',
            },
        )

    if file_size <= 0:
        if range_header:
            unsatisfiable()
        return 0, -1, False

    if not range_header:
        return 0, file_size - 1, False

    # Multi-range responses are intentionally unsupported.
    if ',' in range_header:
        unsatisfiable('Multiple byte ranges are not supported')

    range_match = re_fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
    if not range_match:
        unsatisfiable()

    raw_start, raw_end = range_match.groups()
    if not raw_start and not raw_end:
        unsatisfiable()

    if not raw_start:
        # Suffix range: bytes=-500 means the last 500 bytes.
        suffix_len = int(raw_end)
        if suffix_len <= 0:
            unsatisfiable()
        start = max(file_size - suffix_len, 0)
        end = file_size - 1
    else:
        start = int(raw_start)
        if start >= file_size:
            unsatisfiable()
        end = int(raw_end) if raw_end else file_size - 1
        end = min(end, file_size - 1)
        if start > end:
            unsatisfiable()

    return start, end, True


async def _get_stream_message(channel_id, message_id):
    """Fetch media with a round-robin worker and return the client that owns it."""
    preferred = get_worker_client()
    clients = [preferred]
    if preferred != TelegramBot:
        clients.append(TelegramBot)

    last_error = None
    for client in clients:
        try:
            message = await client.get_messages(chat_id=channel_id, message_ids=message_id)
            if message and not getattr(message, 'empty', False):
                return message, client
        except Exception as exc:
            last_error = exc

    if last_error:
        logger.warning(
            "Unable to fetch Telegram media %s/%s for streaming: %s",
            channel_id,
            message_id,
            last_error,
        )
    return None, None

@bp.route('/')
async def home():
    return redirect(f'https://t.me/{Telegram.BOT_USERNAME}')

@bp.route('/ping')
@bp.route('/health')
async def health_check():
    return "OK", 200

# ==================== STREAM & DOWNLOAD ROUTES ====================

@bp.route('/dl/<string:file_code>')
async def transmit_file(file_code):
    # Lookup file record in MongoDB
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    channel_id = doc.get('channel_id')
    message_id = doc.get('message_id')

    # Use a round-robin worker for the entire request. If that worker cannot
    # access the channel, fall back to the primary bot.
    file_msg, stream_client = await _get_stream_message(channel_id, message_id)
    if not file_msg:
        abort(404, 'Media message not found in channel.')

    file_name = doc.get('file_name')
    file_size = doc.get('file_size')
    mime_type = doc.get('mime_type')

    # Fallback to inspecting message if metadata is incomplete
    if not file_name or not file_size or not mime_type:
        f_name, f_size, m_type, _, _ = get_file_properties(file_msg)
        file_name = file_name or f_name
        file_size = file_size or f_size
        mime_type = mime_type or m_type

    file_size = int(file_size or 0)
    if file_size <= 0:
        abort(404, 'File metadata is incomplete or unavailable.')

    range_header = request.headers.get('Range')
    start, end, is_partial = _parse_byte_range(range_header, file_size)
    chunk_size = 1024 * 1024  # 1 MB

    total_bytes_to_stream = end - start + 1
    content_length = total_bytes_to_stream
    disposition = 'inline' if request.args.get('inline') == '1' else 'attachment'
    headers = {
        'Content-Type': mime_type or 'application/octet-stream',
        'Content-Disposition': _content_disposition(file_name, disposition),
        'Accept-Ranges': 'bytes',
        'Content-Length': str(content_length),
        'Access-Control-Allow-Origin': '*',
    }
    if is_partial:
        headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    status_code = 206 if is_partial else 200

    async def file_stream():
        bytes_streamed = 0
        current_start = start
        offset = current_start // chunk_size
        remaining_total = end - current_start + 1
        chunks_needed = ceil(remaining_total / chunk_size)

        try:
            chunk_index = 0
            async for chunk in stream_client.stream_media(
                file_msg,
                offset=offset,
                limit=chunks_needed,
            ):
                if chunk_index == 0:
                    trim_start = current_start % chunk_size
                    if trim_start > 0:
                        chunk = chunk[trim_start:]

                remaining_bytes = content_length - bytes_streamed
                if remaining_bytes <= 0:
                    break

                if len(chunk) > remaining_bytes:
                    chunk = chunk[:remaining_bytes]

                yield chunk
                bytes_streamed += len(chunk)
                chunk_index += 1
        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception as e:
            logger.warning("Stream error on %s: %s", getattr(stream_client, 'name', 'Telegram client'), e)
        finally:
            if bytes_streamed > 0:
                await add_bandwidth_bytes(bytes_streamed)
            flush_ram()

    return Response(file_stream(), headers=headers, status=status_code)

@bp.route('/stream/<string:file_code>')
async def stream_file(file_code):
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    media_url = f'{Server.BASE_URL}/dl/{file_code}?inline=1'
    mime_type = (doc.get('mime_type') or 'application/octet-stream').lower()
    if not (mime_type.startswith('video/') or mime_type.startswith('audio/')):
        # A player page is meaningless for PDFs/images/archives/etc. Keep the
        # /stream URL useful by falling back to the direct file response.
        return redirect(media_url)

    return await render_template(
        'player.html',
        mediaLink=media_url,
        fileName=doc.get('file_name', 'Play Media'),
        mimeType=mime_type,
    )

# ==================== REST API ENDPOINTS FOR STREAMHUB ====================

@bp.route('/api/batch/<string:batch_id>')
async def api_get_batch(batch_id):
    """Returns structured JSON for a specific anime or web series batch."""
    for col in (db.anime, db.webseries):
        if col is not None:
            doc = await col.find_one({'_id': batch_id})
            if doc:
                episodes = []
                for ep in doc.get('episodes', []):
                    code = ep['code']
                    episodes.append({
                        'episode_num': ep.get('episode_num', 1),
                        'file_name': ep.get('file_name', ''),
                        'file_size': ep.get('file_size', 0),
                        'size_formatted': get_human_size(ep.get('file_size', 0)),
                        'duration': ep.get('duration', 0),
                        'duration_formatted': ep.get('duration_formatted', 'N/A'),
                        'mime_type': ep.get('mime_type', ''),
                        'stream_url': f"{Server.BASE_URL}/stream/{code}",
                        'download_url': f"{Server.BASE_URL}/dl/{code}",
                        'code': code
                    })
                return jsonify({
                    'status': 'success',
                    'batch_id': batch_id,
                    'title': doc.get('title', ''),
                    'category': doc.get('category', ''),
                    'channel_id': doc.get('channel_id'),
                    'total_episodes': len(episodes),
                    'episodes': episodes
                }), 200

    return jsonify({'status': 'error', 'message': 'Batch not found'}), 404

@bp.route('/api/file/<string:file_code>')
async def api_get_file(file_code):
    """Returns structured JSON metadata and streaming links for a single file/movie."""
    doc = await get_file(file_code)
    if not doc:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404

    code = doc.get('code', file_code)
    return jsonify({
        'status': 'success',
        'code': code,
        'file_name': doc.get('file_name', ''),
        'file_size': doc.get('file_size', 0),
        'size_formatted': get_human_size(doc.get('file_size', 0)),
        'duration': doc.get('duration', 0),
        'duration_formatted': doc.get('duration_formatted', 'N/A'),
        'mime_type': doc.get('mime_type', ''),
        'category': doc.get('category', 'movies'),
        'stream_url': f"{Server.BASE_URL}/stream/{code}",
        'download_url': f"{Server.BASE_URL}/dl/{code}"
    }), 200

@bp.route('/api/movies')
async def api_get_movies():
    """Lists indexed movies."""
    if db.movies is None:
        return jsonify({'status': 'error', 'message': 'Database not connected'}), 500
    
    cursor = db.movies.find({'message_id': {'$exists': True}}).sort('created_at', -1).limit(100)
    movies = []
    async for doc in cursor:
        code = doc.get('code', doc.get('_id'))
        movies.append({
            'code': code,
            'file_name': doc.get('file_name', ''),
            'file_size': doc.get('file_size', 0),
            'size_formatted': get_human_size(doc.get('file_size', 0)),
            'duration': doc.get('duration', 0),
            'duration_formatted': doc.get('duration_formatted', 'N/A'),
            'stream_url': f"{Server.BASE_URL}/stream/{code}",
            'download_url': f"{Server.BASE_URL}/dl/{code}"
        })
    return jsonify({'status': 'success', 'count': len(movies), 'movies': movies}), 200

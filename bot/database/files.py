import asyncio
from secrets import token_hex
from datetime import datetime
from pymongo.errors import DuplicateKeyError
from bot.config import Telegram, Server
from bot.database import db

_save_file_lock = asyncio.Lock()
_save_batch_lock = asyncio.Lock()


def _merge_episode_codes(existing: dict, episodes: list[dict]) -> list[dict]:
    """Repair/re-index a batch without invalidating already-issued episode URLs."""
    old_by_message = {
        ep.get('message_id'): ep
        for ep in existing.get('episodes', [])
        if ep.get('message_id') is not None and ep.get('code')
    }
    merged = []
    for episode in episodes:
        item = dict(episode)
        old = old_by_message.get(item.get('message_id'))
        if old and old.get('code'):
            item['code'] = old['code']
        code = item.get('code')
        if code:
            item['dl_link'] = f"{Server.BASE_URL}/dl/{code}"
            item['stream_link'] = f"{Server.BASE_URL}/stream/{code}"
        merged.append(item)
    return merged

async def save_file(
    channel_id: int,
    message_id: int,
    file_name: str,
    file_size: int,
    mime_type: str,
    user_id: int,
    category: str = 'movies',
    title: str = None,
    duration: int = 0,
    duration_formatted: str = "N/A"
) -> dict:
    """Saves a single movie or direct file."""
    collection = db.get_collection(category)
    if collection is None:
        raise RuntimeError("Database is not connected.")

    async with _save_file_lock:
        # Check if this exact channel message is already indexed.
        existing = await collection.find_one({
            'channel_id': channel_id,
            'message_id': message_id
        })
        if existing:
            return existing

        code = token_hex(Telegram.SECRET_CODE_LENGTH)
        doc = {
            '_id': code,
            'code': code,
            'channel_id': channel_id,
            'message_id': message_id,
            'file_name': file_name,
            'file_size': int(file_size or 0),
            'mime_type': mime_type or 'application/octet-stream',
            'duration': int(duration or 0),
            'duration_formatted': duration_formatted or 'N/A',
            'user_id': user_id,
            'category': category.lower(),
            'title': title or file_name,
            'created_at': datetime.utcnow()
        }

        try:
            await collection.insert_one(doc)
            return doc
        except DuplicateKeyError:
            # Another request/process inserted the same channel message first.
            existing = await collection.find_one({
                'channel_id': channel_id,
                'message_id': message_id
            })
            if existing:
                return existing
            raise

async def save_batch(
    channel_id: int,
    start_id: int,
    end_id: int,
    category: str,
    user_id: int,
    episodes: list[dict],
    title: str = None
) -> dict:
    """Saves an entire batch of anime or web series episodes as a SINGLE unified document."""
    normalized_category = category.lower()
    if normalized_category not in ('anime', 'animes', 'series', 'webseries', 'tv'):
        raise ValueError("Batch category must be anime or webseries.")

    collection = db.get_collection(category)
    if collection is None:
        raise RuntimeError("Database is not connected.")

    canonical_category = 'webseries' if normalized_category in ('series', 'webseries', 'tv') else 'anime'
    lookup = {
        'channel_id': channel_id,
        'start_id': start_id,
        'end_id': end_id
    }

    async with _save_batch_lock:
        existing = await collection.find_one(lookup)
        if existing:
            # A prior attempt may have saved an incomplete batch after a transient
            # Telegram failure. Re-indexing the same range repairs it in place.
            merged_episodes = _merge_episode_codes(existing, episodes)
            updates = {
                'episodes': merged_episodes,
                'total_episodes': len(merged_episodes),
                'category': canonical_category,
                'user_id': user_id,
            }
            if title:
                updates['title'] = title
            elif not existing.get('title'):
                updates['title'] = f"{canonical_category.upper()} Batch ({len(episodes)} episodes)"
            await collection.update_one({'_id': existing['_id']}, {'$set': updates})
            existing.update(updates)
            return existing

        batch_code = token_hex(16)
        doc = {
            '_id': batch_code,
            'batch_code': batch_code,
            'title': title or f"{canonical_category.upper()} Batch ({len(episodes)} episodes)",
            'category': canonical_category,
            'channel_id': channel_id,
            'start_id': start_id,
            'end_id': end_id,
            'total_episodes': len(episodes),
            'user_id': user_id,
            'created_at': datetime.utcnow(),
            'episodes': episodes
        }

        try:
            await collection.insert_one(doc)
            return doc
        except DuplicateKeyError:
            existing = await collection.find_one(lookup)
            if existing:
                updates = {
                    'episodes': _merge_episode_codes(existing, episodes),
                    'total_episodes': len(episodes),
                    'category': canonical_category,
                    'user_id': user_id,
                }
                if title:
                    updates['title'] = title
                await collection.update_one({'_id': existing['_id']}, {'$set': updates})
                existing.update(updates)
                return existing
            raise

async def get_file(code: str, category_hint: str = None) -> dict | None:
    """Resolves a file by its unique code, supporting both single documents and episodes inside batch documents."""
    if not code:
        return None

    # 1. Search in single file collections (movies, direct_files)
    for col in (db.movies, db.direct_files):
        if col is not None:
            doc = await col.find_one({'_id': code, 'message_id': {'$exists': True}})
            if doc:
                return doc

    # 2. Search inside batch documents (anime, webseries). A batch ID is not a
    # downloadable file code; only episode codes resolve here.
    for col in (db.anime, db.webseries):
        if col is not None:
            batch_doc = await col.find_one({'episodes.code': code})
            if batch_doc:
                for ep in batch_doc.get('episodes', []):
                    if ep.get('code') == code:
                        return {
                            '_id': ep['code'],
                            'code': ep['code'],
                            'channel_id': batch_doc['channel_id'],
                            'message_id': ep['message_id'],
                            'file_name': ep['file_name'],
                            'file_size': ep['file_size'],
                            'mime_type': ep['mime_type'],
                            'duration': ep.get('duration', 0),
                            'duration_formatted': ep.get('duration_formatted', 'N/A'),
                            'category': batch_doc.get('category', 'anime'),
                            'user_id': batch_doc.get('user_id'),
                            'batch_id': batch_doc['_id']
                        }

    return None


async def get_record(code: str) -> dict | None:
    """Resolve either a single file/episode or a whole batch for admin actions."""
    file_doc = await get_file(code)
    if file_doc:
        return file_doc
    # Also resolve legacy movie-batch documents so admins can revoke them.
    if db.movies is not None:
        legacy_doc = await db.movies.find_one({'_id': code})
        if legacy_doc:
            return legacy_doc
    for col in (db.anime, db.webseries):
        if col is not None:
            batch_doc = await col.find_one({'_id': code})
            if batch_doc:
                return batch_doc
    return None

async def delete_file(code: str) -> bool:
    """Deletes a file or removes an episode from a batch."""
    if not code:
        return False
        
    # Delete from single file collections
    for col in (db.movies, db.direct_files):
        if col is not None:
            res = await col.delete_one({'_id': code})
            if res.deleted_count > 0:
                return True

    # Delete or pull from batch collections
    for col in (db.anime, db.webseries):
        if col is not None:
            # Delete whole batch if batch code matched
            res = await col.delete_one({'_id': code})
            if res.deleted_count > 0:
                return True
            
            # Otherwise pull a single episode from its owning batch.
            batch_doc = await col.find_one({'episodes.code': code}, {'_id': 1, 'episodes': 1})
            if not batch_doc:
                continue
            res = await col.update_one(
                {'_id': batch_doc['_id'], 'episodes.code': code},
                {'$pull': {'episodes': {'code': code}}}
            )
            if res.modified_count > 0:
                remaining_count = max(0, len(batch_doc.get('episodes', [])) - 1)
                await col.update_one(
                    {'_id': batch_doc['_id']},
                    {'$set': {'total_episodes': remaining_count}}
                )
                return True

    return False

async def add_bandwidth_bytes(byte_count: int):
    try:
        if db.db is not None and byte_count > 0:
            await db.db['analytics'].update_one(
                {'_id': 'bandwidth'},
                {'$inc': {'bytes_streamed': byte_count, 'requests': 1}},
                upsert=True
            )
    except Exception:
        pass

async def get_bandwidth_stats() -> tuple[int, int]:
    try:
        if db.db is not None:
            doc = await db.db['analytics'].find_one({'_id': 'bandwidth'})
            if doc:
                return doc.get('bytes_streamed', 0), doc.get('requests', 0)
    except Exception:
        pass
    return 0, 0

async def get_stats() -> dict:
    stats = {
        'movies': 0,
        'anime': 0,
        'webseries': 0,
        'direct_files': 0
    }
    
    if db.movies is not None:
        stats['movies'] = await db.movies.count_documents({'message_id': {'$exists': True}})
    if db.direct_files is not None:
        stats['direct_files'] = await db.direct_files.count_documents({})

    # Count total episodes across all batches in anime and webseries
    for name, col in (('anime', db.anime), ('webseries', db.webseries)):
        if col is not None:
            pipeline = [
                {'$project': {'count': {'$size': {'$ifNull': ['$episodes', []]}}}},
                {'$group': {'_id': None, 'total': {'$sum': '$count'}}}
            ]
            cursor = col.aggregate(pipeline)
            docs = await cursor.to_list(length=1)
            stats[name] = docs[0]['total'] if docs else 0

    return stats

async def search_records(query: str, limit: int = 30) -> list[dict]:
    """Searches across movies, anime, webseries, and direct files by title or filename with smart multi-word matching."""
    import re
    from bot.config import Server
    from bot.modules.static import get_human_size

    if not query or not query.strip():
        return []

    clean_q = query.strip()
    words = [re.escape(w) for w in clean_q.split() if len(w) > 1]
    phrase_pattern = re.compile(re.escape(clean_q), re.IGNORECASE)

    # Build smart multi-word token filters (matches docs containing query words)
    if words:
        single_word_conds = [
            {
                '$or': [
                    {'file_name': {'$regex': w, '$options': 'i'}},
                    {'title': {'$regex': w, '$options': 'i'}}
                ]
            }
            for w in words
        ]
        single_filter = {'$or': [{'file_name': {'$regex': phrase_pattern}}, {'title': {'$regex': phrase_pattern}}, {'$and': single_word_conds}]}

        batch_word_conds = [
            {
                '$or': [
                    {'title': {'$regex': w, '$options': 'i'}},
                    {'episodes.file_name': {'$regex': w, '$options': 'i'}}
                ]
            }
            for w in words
        ]
        batch_filter = {'$or': [{'title': {'$regex': phrase_pattern}}, {'episodes.file_name': {'$regex': phrase_pattern}}, {'$and': batch_word_conds}]}
    else:
        single_filter = {'$or': [{'file_name': {'$regex': phrase_pattern}}, {'title': {'$regex': phrase_pattern}}]}
        batch_filter = {'$or': [{'title': {'$regex': phrase_pattern}}, {'episodes.file_name': {'$regex': phrase_pattern}}]}

    results = []

    # 1. Search in single files (movies, direct_files)
    for col, cat_name in ((db.movies, 'movies'), (db.direct_files, 'direct_files')):
        if col is not None and len(results) < limit:
            file_filter = {'$and': [{'message_id': {'$exists': True}}, single_filter]}
            cursor = col.find(file_filter).sort('created_at', -1).limit(limit - len(results))

            async for doc in cursor:
                code = doc.get('code', doc.get('_id'))
                results.append({
                    'type': 'movie',
                    'category': cat_name,
                    'code': code,
                    'title': doc.get('title') or doc.get('file_name'),
                    'file_name': doc.get('file_name'),
                    'file_size': doc.get('file_size', 0),
                    'mime_type': doc.get('mime_type', 'application/octet-stream'),
                    'size_formatted': get_human_size(doc.get('file_size', 0)),
                    'duration': doc.get('duration', 0),
                    'duration_formatted': doc.get('duration_formatted', 'N/A'),
                    'stream_url': f"{Server.BASE_URL}/stream/{code}",
                    'download_url': f"{Server.BASE_URL}/dl/{code}",
                    'api_url': f"{Server.BASE_URL}/api/file/{code}"
                })

    # 2. Search in batches (anime, webseries)
    for col, cat_name in ((db.anime, 'anime'), (db.webseries, 'webseries')):
        if col is not None and len(results) < limit:
            cursor = col.find(batch_filter).sort('created_at', -1).limit(limit - len(results))

            async for batch_doc in cursor:
                batch_id = batch_doc.get('_id')
                episodes = batch_doc.get('episodes', [])
                total_size = sum(ep.get('file_size', 0) for ep in episodes)
                
                formatted_episodes = []
                for ep in episodes:
                    code = ep['code']
                    formatted_episodes.append({
                        'episode_num': ep.get('episode_num', 1),
                        'file_name': ep.get('file_name', ''),
                        'file_size': ep.get('file_size', 0),
                        'size_formatted': get_human_size(ep.get('file_size', 0)),
                        'duration': ep.get('duration', 0),
                        'duration_formatted': ep.get('duration_formatted', 'N/A'),
                        'stream_url': f"{Server.BASE_URL}/stream/{code}",
                        'download_url': f"{Server.BASE_URL}/dl/{code}",
                        'code': code
                    })

                results.append({
                    'type': 'batch',
                    'category': cat_name,
                    'batch_id': batch_id,
                    'title': batch_doc.get('title') or f"{cat_name.upper()} Batch ({len(episodes)} episodes)",
                    'total_episodes': len(episodes),
                    'total_size': total_size,
                    'size_formatted': get_human_size(total_size),
                    'api_url': f"{Server.BASE_URL}/api/batch/{batch_id}",
                    'episodes': formatted_episodes
                })

    return results[:limit]



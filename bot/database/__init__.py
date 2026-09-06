from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import Database
from logging import getLogger

logger = getLogger('bot')

class MongoDatabase:
    def __init__(self):
        self._client = None
        self.db = None
        self.movies = None
        self.anime = None
        self.webseries = None
        self.direct_files = None

    async def connect(self):
        try:
            self._client = AsyncIOMotorClient(
                Database.DATABASE_URL,
                maxPoolSize=10,  # Keep connection pool compact for low RAM
                minPoolSize=1,
                serverSelectionTimeoutMS=10000,
            )
            # Motor is lazy; force a round-trip so startup cannot falsely claim
            # that MongoDB is connected when the URI/host is actually invalid.
            await self._client.admin.command('ping')
            self.db = self._client[Database.DATABASE_NAME]
            self.movies = self.db['movies']
            self.anime = self.db['anime']
            self.webseries = self.db['webseries']
            self.direct_files = self.db['direct_files']
            logger.info("Connected to MongoDB database: %s", Database.DATABASE_NAME)
        except Exception as e:
            logger.error("Failed to connect to MongoDB: %s", e)
            raise e

    async def create_indexes(self):
        """Ensures high-speed O(1) indexes to eliminate query latency and CPU spikes."""
        operations = []
        if self.movies is not None:
            # Reverse the key order from the legacy non-unique index so existing
            # deployments can create this unique index without IndexOptionsConflict.
            operations.append((self.movies, [("message_id", 1), ("channel_id", 1)], {
                'unique': True,
                'name': 'uniq_message_channel',
                'partialFilterExpression': {'message_id': {'$exists': True}},
            }))
        if self.direct_files is not None:
            operations.append((self.direct_files, [("message_id", 1), ("channel_id", 1)], {
                'unique': True,
                'name': 'uniq_message_channel',
                'partialFilterExpression': {'message_id': {'$exists': True}},
            }))
        if self.anime is not None:
            operations.append((self.anime, "episodes.code", {'name': 'episode_code'}))
            operations.append((self.anime, [("start_id", 1), ("end_id", 1), ("channel_id", 1)], {
                'unique': True, 'name': 'uniq_batch_range_channel'
            }))
        if self.webseries is not None:
            operations.append((self.webseries, "episodes.code", {'name': 'episode_code'}))
            operations.append((self.webseries, [("start_id", 1), ("end_id", 1), ("channel_id", 1)], {
                'unique': True, 'name': 'uniq_batch_range_channel'
            }))

        failures = 0
        for collection, keys, kwargs in operations:
            try:
                await collection.create_index(keys, **kwargs)
            except Exception as e:
                failures += 1
                # Existing deployments may already contain duplicates. Keep the bot
                # usable and report the issue instead of crashing startup; save_*
                # also performs in-process de-duplication and DuplicateKey recovery.
                logger.warning("Could not create MongoDB index %s: %s", kwargs.get('name'), e)

        if failures:
            logger.warning("MongoDB index setup completed with %d failure(s).", failures)
        else:
            logger.info("MongoDB database indexes ensured.")

    def close(self):
        if self._client is not None:
            self._client.close()
        self._client = None
        self.db = None
        self.movies = None
        self.anime = None
        self.webseries = None
        self.direct_files = None

    def get_collection(self, category: str):
        cat = category.lower()
        if cat in ('movie', 'movies'):
            return self.movies
        elif cat in ('anime', 'animes'):
            return self.anime
        elif cat in ('series', 'webseries', 'tv'):
            return self.webseries
        else:
            return self.direct_files

db = MongoDatabase()

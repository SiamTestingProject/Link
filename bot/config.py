import os
import re
from os import environ as env

# Auto-load variables from start.sh, .env or config.env if present (supporting multi-line quoted strings)
def _load_env_files():
    for fn in ("start.sh", ".env", "config.env"):
        if os.path.exists(fn):
            try:
                with open(fn, "r", encoding="utf-8") as f:
                    content = f.read()
                matches = re.findall(
                    r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s#]+))',
                    content
                )
                for k, v1, v2, v3 in matches:
                    v = (v1 or v2 or v3 or "").strip()
                    # Resolve bash parameter expansion like ${PORT:-8080}
                    bash_match = re.match(r'^\$\{([A-Za-z_][A-Za-z0-9_]*):-(.*)\}$', v)
                    if bash_match:
                        var_name, default_val = bash_match.groups()
                        v = os.environ.get(var_name, default_val)
                    if k and v:
                        # Hosting/provider environment variables must take precedence
                        # over values committed to or stored in local env files.
                        os.environ.setdefault(k, v)
            except Exception:
                pass

_load_env_files()

def _get_int(val, default=0) -> int:
    try:
        return int(str(val).strip())
    except Exception:
        return default

class Telegram:
    API_ID = _get_int(env.get("TELEGRAM_API_ID", env.get("API_ID", 0)), 0)
    API_HASH = env.get("TELEGRAM_API_HASH", env.get("API_HASH", "")).strip()
    
    # Primary Bot
    BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN", env.get("BOT_TOKEN", "")).strip()
    BOT_USERNAME = env.get("TELEGRAM_BOT_USERNAME", env.get("BOT_USERNAME", "")).strip().lstrip("@")
    
    # Multi-client worker tokens (comma, space, or newline separated)
    _raw_multi_tokens = env.get("MULTI_BOT_TOKENS", env.get("BOT_TOKENS", ""))
    MULTI_BOT_TOKENS = [
        tok.strip() for tok in _raw_multi_tokens.replace(",", " ").split() if tok.strip()
    ]
    # Worker pool combining primary + worker tokens (preserving order, removing duplicates)
    WORKER_TOKENS = list(dict.fromkeys([BOT_TOKEN] + MULTI_BOT_TOKENS)) if MULTI_BOT_TOKENS else [BOT_TOKEN]

    # Owner & Auth/Admin Users
    # There is deliberately no hard-coded owner fallback. A missing OWNER_ID
    # leaves admin access disabled and startup validation will fail safely.
    OWNER_ID = _get_int(env.get("OWNER_ID"), 0)
    _raw_auth_users = env.get("AUTH_USERS", "")
    AUTH_USERS = [
        int(uid.strip()) for uid in _raw_auth_users.replace(",", " ").split() if uid.strip().lstrip("-").isdigit()
    ]
    ADMIN_IDS = {uid for uid in ([OWNER_ID] + AUTH_USERS) if uid}

    # Allowed Users for general usage (empty = everyone allowed)
    ALLOWED_USER_IDS = [
        uid.strip()
        for uid in env.get("ALLOWED_USER_IDS", "").replace(",", " ").split()
        if uid.strip().lstrip("-").isdigit()
    ]
    
    # Optional Storage / Bin Channel ID (Only needed if you upload files directly in private DM)
    CHANNEL_ID = _get_int(env.get("TELEGRAM_CHANNEL_ID", env.get("CHANNEL_ID", env.get("BIN_CHANNEL_ID", 0))), 0)
    SECRET_CODE_LENGTH = _get_int(env.get("SECRET_CODE_LENGTH", 24), 24)

    @classmethod
    def validate(cls):
        missing = []
        if cls.API_ID <= 0:
            missing.append("TELEGRAM_API_ID")
        if not cls.API_HASH:
            missing.append("TELEGRAM_API_HASH")
        if not cls.BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cls.BOT_USERNAME:
            missing.append("TELEGRAM_BOT_USERNAME")
        if cls.OWNER_ID <= 0:
            missing.append("OWNER_ID")

        if missing:
            raise RuntimeError(
                "Missing or invalid required configuration: " + ", ".join(missing)
            )

        if cls.SECRET_CODE_LENGTH < 8:
            raise RuntimeError("SECRET_CODE_LENGTH must be at least 8 bytes.")

class Database:
    DATABASE_URL = env.get("DATABASE_URL", env.get("MONGODB_URI", "mongodb://localhost:27017"))
    DATABASE_NAME = env.get("DATABASE_NAME", "OmniArchiver")

class Server:
    BASE_URL = env.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    BIND_ADDRESS = env.get("BIND_ADDRESS", env.get("IP", "::"))
    if BIND_ADDRESS.startswith("${"):
        BIND_ADDRESS = "::"
    PORT = _get_int(env.get("PORT", 8080), 8080)

# LOGGING CONFIGURATION
LOGGER_CONFIG_JSON = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s][%(name)s][%(levelname)s] -> %(message)s',
            'datefmt': '%d/%m/%Y %H:%M:%S'
        },
    },
    'handlers': {
        'file_handler': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'event-log.txt',
            'maxBytes': 2 * 1024 * 1024,
            'backupCount': 2,
            'formatter': 'default'
        },
        'stream_handler': {
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        }
    },
    'loggers': {
        'uvicorn': {
            'level': 'INFO',
            'handlers': ['file_handler', 'stream_handler']
        },
        'uvicorn.error': {
            'level': 'WARNING',
            'handlers': ['file_handler', 'stream_handler']
        },
        'bot': {
            'level': 'INFO',
            'handlers': ['file_handler', 'stream_handler']
        },
        'hydrogram': {
            'level': 'WARNING',
            'handlers': ['file_handler', 'stream_handler']
        }
    }
}

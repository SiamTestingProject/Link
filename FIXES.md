# OmniArchiver-F2L — Reliability, Security & Alwaysdata Fixes

This build includes the reliability/security repair pass plus deployment hardening added after Alwaysdata testing.

## Security / configuration

- No hard-coded `OWNER_ID`, Telegram token, API hash, MongoDB URI, or other live credential is stored in source.
- `.env.example` now contains blank values instead of token-looking examples.
- `.env`, `config.env`, `start.sh`, logs, local databases, and all Hydrogram session sidecars are ignored by Git.
- Startup fails early when required Telegram, MongoDB, or `BASE_URL` configuration is missing.
- Hosting-provider environment variables take precedence over local env files.
- `/set_title` is admin-only and its MongoDB regex input is escaped.
- Shell-command timeouts terminate the whole spawned process tree and report the real exit code.

## Hydrogram session corruption

- Main and worker bot clients now use `in_memory=True`.
- Persistent `bot_main.session` / `worker_*.session` SQLite files are no longer required or created by this build.
- This prevents stale/corrupt session databases from causing `sqlite3.DatabaseError: database disk image is malformed`.
- Existing deployments should stop all old bot instances and remove legacy session files once with:
  `rm -f bot_main.session* worker_*.session*`.

## Plugin startup

- Handler modules are imported explicitly once instead of relying on Hydrogram Smart Plugins to discover instance-bound decorators.
- This removes the misleading `No plugin loaded from "bot.plugins"` warning while preserving the existing handler registration style.

## File and batch indexing

- Repaired direct-DM upload tuple unpacking, user ID handling, duration metadata, and non-streamable file cards.
- `/batch movies` is rejected instead of creating unusable batch records.
- Batch scanning retries transient Telegram/FloodWait failures and never saves a known-incomplete batch.
- Re-indexing the same range repairs the existing batch while preserving previously issued episode codes.
- Added duplicate-safe save logic and unique MongoDB indexes where existing data permits them.
- Legacy movie-batch records are excluded from normal file/search/API listings but remain revocable by admins.

## HTTP streaming

- Fixed missing exception-handler imports and metadata fallback unpacking.
- Reworked single-byte-range handling: open-ended/suffix ranges, clamping, `206`, and RFC-compatible `416` headers.
- Added safer Unicode `Content-Disposition` generation and header-injection sanitization.
- Requests are distributed across healthy worker clients, with primary-bot fallback, and the selected client performs the stream.
- Non-video/audio `/stream` links fall back to direct delivery.
- Fixed the web player source initialization and click-event handling.

## Commands / API / lifecycle

- Episode sizes now use stored `file_size` values instead of showing `0 B`.
- `/search_api` output is chunked below Telegram's message-size limit.
- `/purge N` now targets exactly N messages.
- MongoDB startup performs an actual ping before reporting success.
- Failed worker bots are removed from the active round-robin pool.
- Web-server failure is monitored and shutdown cancels services cleanly and closes MongoDB.
- Dependencies are pinned for reproducible deployments.

## Alwaysdata documentation

- README now documents the tested `git clone` → Python 3.11 → venv → `.env` → User Program flow.
- Alwaysdata `IP` and `PORT` are provider-managed; `BIND_ADDRESS` and `PORT` should be omitted from `.env` there.
- The Free-plan custom-domain restriction is documented.
- Health checks, logs, MongoDB SRV troubleshooting, worker-token behavior, updates, and one-time legacy session cleanup are documented.

## Validation

- Existing regression tests cover HTTP byte ranges, Unicode download headers, Telegram link parsing, and size/duration formatting.
- Source changes are Python-syntax checked before release.

# OmniArchiver-F2L 2.0.1 — Reliability & Security Fixes

This maintenance release repairs the confirmed runtime, authorization, streaming, indexing, and deployment issues found during review.

## Security / configuration
- Removed the hard-coded `OWNER_ID` fallback and fail startup when required Telegram/admin settings are missing.
- Hosting-provider environment variables now override local env/start files.
- `/set_title` is admin-only and its MongoDB regex input is escaped.
- Shell-command timeouts terminate the whole spawned process tree and report the real exit code.
- Local secret-bearing files (`start.sh`, `config.env`) and restart state are ignored by Git.

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
- Web-server failure is monitored and shutdown now cancels services cleanly and closes MongoDB.
- Dependencies are pinned for reproducible deployments.

## Validation
- Python compilation passes for the complete project.
- Added regression tests for HTTP byte ranges, Unicode download headers, Telegram link parsing, and size/duration formatting.

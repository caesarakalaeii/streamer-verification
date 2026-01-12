# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **New `/whois` Command** (2025-12-18)
  - Look up any Discord user's verified Twitch name
  - One-way lookup only (Discord → Twitch) to protect streamer privacy
  - Works in DMs, servers, and private channels
  - Ephemeral responses (only visible to command user)
  - Available to all users, not just admins
  - Supports both guild and user installations

- **User Install Support** (2025-12-18)
  - Bot can now be installed directly to user accounts
  - Enables `/whois` usage without joining any server
  - Configured via `@app_commands.allowed_installs(guilds=True, users=True)`
  - Configured via `@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)`

- **Pre-commit Hooks Setup** (2025-12-18)
  - Automated code quality checks on commit
  - Includes: black (formatting), ruff (linting), mypy (type checking)
  - Standard checks: trailing whitespace, end of files, YAML validation
  - Updated Python version compatibility to python3 (supports 3.13+)

### Changed
- Updated `.pre-commit-config.yaml` to use `python3` instead of `python3.11`
- Added `UserVerificationRepository` import to `src/bot/commands.py`
- Added `noqa: E402` comments to `scripts/init_db.py` for legitimate import ordering
- Impersonation detection now queries streamer cache via PostgreSQL trigram
  similarity instead of loading every entry into memory
- `scripts/init_db.py` executes every SQL migration (including pg_trgm extension)
  to keep the database schema in sync

### Documentation
- Updated README.md with new `/whois` command documentation
- Added "Recent Updates" section to README
- Added user install setup instructions for Discord Developer Portal
- Added pre-commit hooks documentation
- Documented privacy features of `/whois` command
- Documented pg_trgm-backed cache lookups in README and
  `IMPERSONATION_DETECTION.md`

## Purpose of `/whois` Command

The `/whois` command was designed with privacy and usability in mind:

**Privacy Protection:**
- ✅ Only supports Discord → Twitch lookup
- ❌ Does NOT support Twitch → Discord reverse lookup
- ✅ Prevents users from searching for a streamer's Discord account
- ✅ Only allows verifying if a specific Discord user is a particular streamer

**Use Cases:**
- Verify that a Discord user is who they claim to be on Twitch
- Check verified status without needing server admin permissions
- Works across all contexts (DMs, servers, private channels)
- No server required when using user install

**Technical Implementation:**
- Uses `UserVerificationRepository.get_by_discord_id()` (one-way lookup)
- Does not expose `get_by_twitch_id()` via commands
- Responses are ephemeral (private to command user)
- Supports user installations for maximum accessibility

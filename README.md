# Discord-Twitch Verification Bot (Linked Roles)

A Python-based Discord bot that uses **Discord Linked Roles** to securely verify users via Twitch OAuth, automatically sets their Discord nickname to their Twitch username, and periodically enforces these nicknames.

## Recent Updates

### Latest Changes
- ✨ **New `/whois` Command**: Look up any Discord user's verified Twitch name
  - Works in DMs and servers
  - Privacy-focused: One-way lookup only (Discord → Twitch, not reverse)
  - Available to everyone, not just admins
  - Ephemeral responses (only visible to you)
- 🔧 **User Install Support**: Bot can now be added directly to user accounts
  - No server required to use `/whois`
  - Commands work in DMs and private channels
  - Configured via Discord Developer Portal Installation settings
- 🛠️ **Pre-commit Hooks**: Automated code quality checks
  - black, ruff, mypy, and standard checks
  - Runs automatically on git commit
  - Ensures consistent code style

## Features

- ✅ **Multi-Server Support**: Add to any server - each has its own configuration
- ✅ **User Install Support**: Users can add the bot directly to their account (no server required)
- ✅ **Zero Redeployment**: No code changes needed to add new servers
- ✅ **Per-Guild Configuration**: Each server owner configures their own roles and settings
- ✅ **Discord Native Integration**: Uses Discord's official Linked Roles API
- ✅ **Built-in Security**: Discord handles OAuth flow - impossible to share links
- ✅ **Profile Integration**: Twitch username appears in Discord user profile
- ✅ **1-to-1 Mapping**: Enforces strict 1 Discord user = 1 Twitch account relationship
- ✅ **Automatic Nickname Management**: Sets and enforces Discord nicknames to match Twitch usernames
- ✅ **Periodic Enforcement**: Checks and updates nicknames every 5 minutes (configurable per guild)
- ✅ **Automatic Role Assignment**: Discord assigns role when metadata requirements are met
- ✅ **User Lookup**: `/whois` command to look up Discord user's Twitch name (one-way only, privacy-focused)
- ✅ **Admin Commands**: `/setup`, `/unverify`, `/list-verified`, `/config` for server management
- ✅ **Audit Logging**: Complete audit trail of all verification actions
- ✅ **Docker Ready**: Fully containerized with Docker Compose
- ✅ **CI/CD Pipeline**: GitHub Actions for automated testing and deployment

## How It Works

### 🌟 Verify Once, Works Everywhere

**The best part:** Users verify **once** and are automatically verified in **all servers** using this bot!

- User verifies in Server A → Metadata stored on their Discord profile globally
- User joins Server B (also using this bot) → **Automatically gets verified role** ✅
- User joins Server C (also using this bot) → **Automatically gets verified role** ✅
- No re-verification needed!

### User Experience

1. User goes to **Discord Settings → Connections**
2. Finds your app in the list and clicks **"Link"**
3. Authenticates with Discord (native OAuth)
4. Redirects to your web app
5. Clicks **"Connect with Twitch"**
6. Authenticates with Twitch
7. ✅ **Done!** Their profile shows "Verified on Twitch"
8. They get the verified role automatically in **current server**
9. They get the verified role automatically in **all future servers** they join that use this bot

### Behind the Scenes

```
User clicks "Link" in Discord Profile
         ↓
Discord OAuth (built-in, secure)
         ↓
Web App: Exchange Discord token
         ↓
Redirect to Twitch OAuth
         ↓
Create verification in database
         ↓
Push metadata to Discord API
         ↓
Discord automatically assigns role
         ↓
Bot enforces nickname periodically
```

### Why Linked Roles is Better

| Aspect | Old Approach (Custom) | Linked Roles Approach ✅ |
|--------|----------------------|--------------------------|
| **Security** | Custom dual OAuth | Discord native (impossible to share) |
| **User Experience** | Custom web pages | Native Discord UI |
| **Role Assignment** | Bot assigns manually | Discord assigns automatically |
| **Profile Integration** | No | Yes - shows in profile |
| **Code Complexity** | High | Lower |
| **Maintenance** | More | Less |

## Architecture

```
┌─────────────────────────────┐
│   Discord User Profile      │
│   Settings → Connections    │
└──────┬──────────────────────┘
       │ Clicks "Link"
       v
┌─────────────────────────────┐
│   Discord OAuth (Native)    │
│   Redirects to /linked-role │
└──────┬──────────────────────┘
       │
       v
┌─────────────────────────────┐
│   Web Server (FastAPI)      │
│   - Twitch OAuth            │
│   - Push metadata to Discord│
└──────┬──────────────────────┘
       │
       v
┌─────────────────────────────┐
│   PostgreSQL Database       │
│   - user_verifications      │
│   - audit_log              │
└─────────────────────────────┘
       │
       v
┌─────────────────────────────┐
│   Discord Bot (discord.py)  │
│   - Nickname enforcement    │
│   - Admin commands          │
└─────────────────────────────┘
```

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker & Docker Compose (for containerized deployment)
- Discord Bot Application
- Twitch Application

## Setup

### 1. Discord Application Setup

#### Create Application
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Give it a name (e.g., "Twitch Verification")

#### Configure Bot
1. Go to **Bot** section:
   - Enable "Presence Intent"
   - Enable "Server Members Intent"
   - Copy the bot token → Save as `DISCORD_BOT_TOKEN`

2. Bot permissions needed:
   - Manage Nicknames
   - Manage Roles

#### Configure OAuth2
1. Go to **OAuth2 → General** section:
   - Copy **Client ID** → Save as `DISCORD_OAUTH_CLIENT_ID`
   - Copy **Client Secret** → Save as `DISCORD_OAUTH_CLIENT_SECRET`

2. Add **Redirect URL**:
   - URL: `http://your-domain.com/linked-role`
   - This is where Discord will send users after they click "Link"

#### Set Up Linked Roles
1. Go to **General Information** section
2. Scroll to **Linked Roles Verification URL**
3. Enter: `http://your-domain.com/linked-role`
4. Save changes

#### Enable User Install (Optional but Recommended)
1. Go to **Installation** section
2. Under **Installation Contexts**, enable:
   - ✅ Guild Install (for server installations)
   - ✅ User Install (allows users to add bot to their account)
3. Under **Install Link**, select "Discord Provided Link"
4. Under **Default Install Settings**:
   - For Guild Install: Add scopes `bot` and `applications.commands`, permissions: Manage Nicknames, Manage Roles
   - For User Install: Add scope `applications.commands` only
5. Save changes

#### Invite Bot to Server
1. Go to **OAuth2 → URL Generator**
2. Select scopes:
   - `bot`
   - `applications.commands`
3. Select bot permissions:
   - Manage Nicknames
   - Manage Roles
4. Copy the generated URL and open it to invite the bot

**Note**: With user install enabled, users can also add the bot directly to their account using the Discord Provided Link from the Installation section.

### 2. Twitch Application Setup

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Click **"Register Your Application"**
3. Name: Choose a name
4. OAuth Redirect URL: `http://your-domain.com/twitch-callback`
5. Category: Choose appropriate category
6. Create application
7. Copy **Client ID** → Save as `TWITCH_CLIENT_ID`
8. Generate **Client Secret** → Save as `TWITCH_CLIENT_SECRET`

### 3. Deploy the Bot

**One-Time Deployment** - After this, you can add the bot to unlimited servers with no redeployment!

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Discord Bot
DISCORD_BOT_TOKEN=your_bot_token

# Discord OAuth (for Linked Roles)
DISCORD_OAUTH_CLIENT_ID=your_application_id
DISCORD_OAUTH_CLIENT_SECRET=your_client_secret
DISCORD_LINKED_ROLE_VERIFICATION_URL=http://your-domain.com/linked-role

# Twitch OAuth
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret
TWITCH_REDIRECT_URI=http://your-domain.com/twitch-callback

# Web Server
WEB_BASE_URL=http://your-domain.com

# Database
DATABASE_PASSWORD=your_secure_password
```

Deploy once (see Deployment section below).

### 4. Configure Each Server (Done by Server Owners)

**For each Discord server where you add the bot:**

#### Step 1: Create a Role with Linked Role Requirement

1. Create a role (e.g., "✅ Verified Streamer")
2. Copy the role ID (right-click → Copy ID)
3. Edit role → Go to **Links** tab
4. Click **"Add Requirement"**
5. Select your application
6. Set requirement: **"Verified on Twitch"** = ✅
7. Save

#### Step 2: Run `/setup` Command

In your Discord server, run:

```
/setup verified_role:@YourVerifiedRole admin_roles:@Moderator,@Admin
```

- `verified_role`: The role you just created
- `admin_roles`: (Optional) Roles that can use `/unverify` and `/list-verified`

The bot will confirm setup and provide instructions.

**That's it!** No redeployment needed. Repeat for each server.

## Deployment

### Docker Compose (Recommended)

```bash
# Start services
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f bot

# Stop services
docker-compose -f docker/docker-compose.yml down
```

### Manual Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Run bot
python src/main.py
```

## Usage

### For Server Owners (First Time Setup)

#### `/setup`
Configure the bot for your server (one-time setup).

```
/setup verified_role:@Verified Streamer admin_roles:@Moderator
```

Parameters:
- `verified_role`: The role to assign to verified users (must have Linked Role requirement)
- `admin_roles`: (Optional) Comma-separated roles that can use admin commands

After setup, users can start verifying!

### For Users

1. Open **Discord Settings** (gear icon)
2. Go to **Connections**
3. Find the bot's app in the list
4. Click **"Link"**
5. Authenticate with Discord (native flow)
6. Click "Connect with Twitch"
7. Authenticate with Twitch
8. Done! Your profile shows your Twitch connection
9. You automatically get the verified role

### For Everyone (User Install)

#### User Install Feature

You can add this bot directly to your Discord account without joining any server:

1. Click the bot's invite link with **user install enabled**
2. Select "Add to account" instead of selecting a server
3. Use `/whois` command anywhere in DMs or servers

This lets you look up any Discord user's verified Twitch name without needing server permissions.

#### `/whois @user`
Look up a Discord user's verified Twitch name (available to everyone).

```
/whois @username
```

**Privacy Features:**
- ✅ **One-way lookup only**: Discord → Twitch (prevents reverse lookup of streamers)
- ✅ **Works in DMs**: No server required when user-installed
- ✅ **Works in servers**: Also available in any server with the bot
- ✅ **Ephemeral responses**: Results only visible to you

### For Server Admins

#### `/config`
View or update server configuration (admin only).

```
/config
/config verified_role:@NewRole
/config nickname_enforcement:True
```

#### `/unverify @user`
Removes a user's verification (admin only).

```
/unverify @username
```

#### `/list-verified`
Shows all verified users in your server with their Twitch usernames (admin only).

```
/list-verified
```

## Configuration Options

### Environment Variables (One-Time Deployment Config)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | - | Discord bot token |
| `DISCORD_OAUTH_CLIENT_ID` | Yes | - | Discord application ID |
| `DISCORD_OAUTH_CLIENT_SECRET` | Yes | - | Discord OAuth client secret |
| `DISCORD_LINKED_ROLE_VERIFICATION_URL` | Yes | - | Linked roles verification URL |
| `TWITCH_CLIENT_ID` | Yes | - | Twitch client ID |
| `TWITCH_CLIENT_SECRET` | Yes | - | Twitch client secret |
| `TWITCH_REDIRECT_URI` | Yes | - | Twitch OAuth redirect URI |
| `WEB_BASE_URL` | Yes | - | Public-facing URL |
| `WEB_HOST` | No | 0.0.0.0 | Web server host |
| `WEB_PORT` | No | 8080 | Web server port |
| `DATABASE_HOST` | Yes | postgres | PostgreSQL host |
| `DATABASE_NAME` | Yes | streamer_verification | Database name |
| `DATABASE_USER` | Yes | bot_user | Database user |
| `DATABASE_PASSWORD` | Yes | - | PostgreSQL password |
| `NICKNAME_CHECK_INTERVAL_SECONDS` | No | 300 | Nickname check frequency |
| `LOG_LEVEL` | No | INFO | Logging level |

### Per-Guild Settings (Configured via `/setup` Command)

Each server owner configures their own:
- **Verified Role**: Which role to assign verified users
- **Admin Roles**: Which roles can use admin commands
- **Nickname Enforcement**: Enable/disable for their server
- **Auto Role Assignment**: Enable/disable for their server

These are stored in PostgreSQL and can be updated without redeployment.

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_AUDIT_LOGGING` | true | Enable audit logging |
| `ENABLE_NICKNAME_ENFORCEMENT` | true | Enable periodic nickname checks |
| `DEBUG_MODE` | false | Enable debug mode |

## Database Schema

### guild_config
Per-guild configuration (verified role, admin roles, settings). One row per Discord server.

### user_verifications
Stores Discord ↔ Twitch mappings with UNIQUE constraints to enforce 1-to-1 relationship. Global across all servers.

### verification_audit_log
Complete audit trail of all verification actions for security monitoring. Includes guild_id to track which server.

## Development

### Setup Development Environment

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks (recommended)
pipx install pre-commit
pre-commit install

# Pre-commit will now run automatically on git commit
# To run manually on all files:
pre-commit run --all-files
```

### Pre-commit Hooks

The project uses pre-commit hooks for code quality:
- **black**: Code formatting
- **ruff**: Linting and auto-fixes
- **mypy**: Type checking
- **trailing-whitespace**: Remove trailing whitespace
- **end-of-file-fixer**: Ensure files end with newline
- **check-yaml**: Validate YAML files
- **check-added-large-files**: Prevent large files
- **check-merge-conflict**: Detect merge conflicts

### Running Tests

```bash
# Run tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Linting and Type Checking

```bash
# Run all pre-commit hooks manually
pre-commit run --all-files

# Or run individual tools:
ruff check src/
mypy src/
black src/
```

## Troubleshooting

### "Link" button doesn't appear in Discord Connections
- Verify you set the **Linked Roles Verification URL** in Discord Developer Portal
- Make sure URL is publicly accessible
- Check application is not in development mode

### Users link but don't get role
- Ensure you created a role with **Linked Role requirement**
- Requirement must be: your app → "Verified on Twitch" = ✅
- Check bot has "Manage Roles" permission

### Bot can't change nicknames
- Bot's role must be higher than verified users' roles in hierarchy
- Verify bot has "Manage Nicknames" permission
- Check server boost level doesn't override

### Metadata not registering
- Check `DISCORD_BOT_TOKEN` is correct
- Verify bot has been added to at least one server
- Check logs for registration errors on startup

### Commands don't appear in server
- Wait up to 1 hour for Discord to sync commands globally
- Try kicking and re-inviting the bot
- Check bot has `applications.commands` scope

### Server owner can't run `/setup`
- Ensure they are the actual server owner or have Administrator permission
- Check bot permissions are correct
- Try running in a channel where the bot has message permissions

### Want to change settings after `/setup`
- Currently requires database update (future: add `/config` command)
- Use `/unverify` and `/list-verified` for user management

## Multi-Server Architecture

### Deploy Once, Use Everywhere

This bot supports **unlimited Discord servers** with a single deployment:

- ✅ Add the bot to any server you're admin on
- ✅ Each server owner runs `/setup` to configure their server
- ✅ Each server has independent settings (roles, admin permissions)
- ✅ User verifications are global (verify once, works everywhere)
- ✅ Nickname enforcement respects each server's configuration
- ✅ No redeployment or code changes needed for new servers

### Global vs Per-Guild

| Aspect | Scope | Details |
|--------|-------|---------|
| **User Verification** | Global | 1 Discord user = 1 Twitch account across all servers |
| **Verified Role** | Per-Guild | Each server chooses their own verified role |
| **Admin Roles** | Per-Guild | Each server defines who can use admin commands |
| **Nickname Enforcement** | Per-Guild | Can be enabled/disabled per server |
| **Audit Logs** | Global | Track which guild each action occurred in |

### How It Works

1. Bot deployed once with OAuth credentials
2. Server owner invites bot to their server
3. Server owner creates role with Linked Role requirement
4. Server owner runs `/setup` with their preferred role
5. Configuration stored in `guild_config` table
6. Users verify once → metadata stored globally on their Discord profile
7. User gets verified role in **all configured servers** automatically (current + future)

## How Linked Roles Prevents Link Sharing

Unlike custom OAuth flows, Discord Linked Roles makes link sharing **impossible**:

1. User initiates from **their own Discord profile**
2. Discord generates unique OAuth code tied to that specific user
3. Our app receives the code and can only update **that user's** metadata
4. Even if someone shares the callback URL, it won't work for anyone else

This is **built into Discord's OAuth system** - no custom validation needed!

## Architecture Decisions

### Why Linked Roles?
- **Native Integration**: Discord built this feature specifically for this use case
- **Better Security**: OAuth flow handled by Discord, impossible to game
- **Better UX**: Users familiar with Discord Connections UI
- **Less Code**: No need for custom dual OAuth, session management, token validation
- **More Reliable**: Leverage Discord's infrastructure

### Why Still Enforce Nicknames?
Even though Discord assigns roles automatically, users can still manually change their nicknames. The bot's periodic check ensures nicknames stay synchronized with Twitch usernames.

### Why Keep Database?
- Track verification history
- Audit logging for compliance
- Support admin commands (`/unverify`, `/list-verified`)
- Enable future features (re-verification, analytics)

## Resources

- [Discord Linked Roles Official Guide](https://discord.com/developers/docs/tutorials/configuring-app-metadata-for-linked-roles)
- [Discord Linked Roles Sample Code](https://github.com/discord/linked-roles-sample)
- [Twitch API Documentation](https://dev.twitch.tv/docs/api/)

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

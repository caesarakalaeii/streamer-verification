# Troubleshooting User Install & DM Commands

This guide helps you enable user install so the `/whois` command works in DMs.

## Prerequisites

The `/whois` command has been added to the code with these decorators:
```python
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
```

This allows the command to work in both servers and DMs, but **you must configure Discord Developer Portal**.

## Step 1: Configure Discord Developer Portal

### Enable User Install

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Navigate to **Installation** (in the left sidebar)
4. Under **Installation Contexts**, check:
   - ✅ **Guild Install** (for server installations)
   - ✅ **User Install** (for user account installations)

### Configure Install Settings

Still in the **Installation** section:

#### For Guild Install:
1. Under **Default Install Settings** → **Guild Install**
2. Add **Scopes**:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Add **Permissions**:
   - ✅ Manage Nicknames
   - ✅ Manage Roles

#### For User Install:
1. Under **Default Install Settings** → **User Install**
2. Add **Scopes**:
   - ✅ `applications.commands` (only this one - no bot permissions needed)
3. **Do NOT add bot permissions** for user install (they don't apply in DMs)

### Set Install Link

1. Under **Install Link**, select:
   - ✅ **Discord Provided Link** (recommended)

   OR

   - ⚙️ **Custom URL** (if you want to use OAuth2 URL Generator)

2. **Save Changes**

## Step 2: Get the Correct Invite Link

### Option A: Discord Provided Link (Recommended)

1. In the **Installation** section, copy the **Discord Provided Link**
2. This link automatically supports both guild and user installs
3. Share this link with users

### Option B: OAuth2 URL Generator

1. Go to **OAuth2** → **URL Generator**
2. Under **Integration Type**, you'll now see TWO options:
   - **Guild Install** - for adding to servers
   - **User Install** - for adding to user accounts

3. Select **User Install**
4. Check scopes:
   - ✅ `applications.commands`
5. Copy the generated URL
6. Use this URL to add the bot to your user account

## Step 3: Add Bot to Your User Account

### Using the Link

1. Click the invite link (Discord Provided Link or User Install URL)
2. You'll see a dialog with **TWO tabs**:
   - **Add to Server** (guild install)
   - **Use this app everywhere** (user install) ← Select this one!
3. Click **"Use this app everywhere"**
4. Click **"Authorize"**
5. Complete the captcha

### Verify Installation

1. Open Discord
2. Press `/` in any DM or channel
3. Type `whois`
4. You should see the `/whois` command appear

## Step 4: Restart Your Bot

After changing the Discord Developer Portal settings:

```bash
# If running locally
# Stop the bot (Ctrl+C) and restart:
python src/main.py

# If using Docker
docker-compose -f docker/docker-compose.yml restart bot
```

## Step 5: Sync Commands (if needed)

Commands should sync automatically on bot startup. If they don't appear:

### Wait for Global Sync
- Global command sync can take up to **1 hour**
- Be patient - this is a Discord limitation

### Force Sync (Development Only)

Add this temporary code to `src/bot/client.py` in the `on_ready` event:

```python
# DEVELOPMENT ONLY - Remove after testing
await bot.tree.sync()  # Already exists
logger.info(f"Synced {len(bot.tree.get_commands())} global commands")

# Log which commands were synced
for cmd in bot.tree.get_commands():
    logger.info(f"  - /{cmd.name}: {cmd.description}")
    if hasattr(cmd, 'allowed_installs'):
        logger.info(f"    Allowed installs: {cmd.allowed_installs}")
    if hasattr(cmd, 'allowed_contexts'):
        logger.info(f"    Allowed contexts: {cmd.allowed_contexts}")
```

## Common Issues

### Issue 1: Command doesn't appear in DMs

**Cause:** Bot not added as user install, only as guild install

**Solution:**
1. Remove the bot from your connections (User Settings → Connections → Remove)
2. Use the **User Install link** (not the guild install link)
3. Select **"Use this app everywhere"** tab
4. Authorize

### Issue 2: Command appears but fails when used

**Cause:** Missing database connection or bot not running

**Solution:**
1. Check bot logs: `docker-compose -f docker/docker-compose.yml logs bot`
2. Verify database is running: `docker-compose -f docker/docker-compose.yml ps`
3. Check for errors in bot output

### Issue 3: "Interaction failed" error

**Cause:** Bot took too long to respond (>3 seconds)

**Solution:**
1. Check database performance
2. Verify network connectivity
3. Check bot logs for slow queries

### Issue 4: User Install option not showing

**Cause:** Installation contexts not enabled in Developer Portal

**Solution:**
1. Go to Developer Portal → Installation
2. Enable **User Install** checkbox
3. Configure Default Install Settings for User Install
4. Save changes
5. Generate new invite link

### Issue 5: Commands work in servers but not DMs

**Cause:** Command might not have allowed_contexts decorator

**Solution:**
1. Verify `/whois` command has these decorators:
```python
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
```
2. Restart bot
3. Wait for command sync

## Verification Checklist

Use this checklist to verify everything is configured correctly:

### Discord Developer Portal
- [ ] **Installation** section → **Installation Contexts** → **User Install** is checked
- [ ] **Installation** section → **Default Install Settings** → **User Install** has `applications.commands` scope
- [ ] **Install Link** is set to "Discord Provided Link"
- [ ] Changes are saved (green checkmark or success message)

### Bot Code
- [ ] `/whois` command has `@app_commands.allowed_installs(guilds=True, users=True)`
- [ ] `/whois` command has `@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)`
- [ ] Bot is running and connected
- [ ] Commands synced successfully (check logs for "Slash commands synced globally")

### User Account
- [ ] Bot added via **User Install link** (not guild install link)
- [ ] Selected **"Use this app everywhere"** tab during authorization
- [ ] Bot appears in User Settings → Connections
- [ ] `/whois` command appears when typing `/` in DMs

## Testing the Command

Once everything is set up:

1. Open a DM with yourself or a friend
2. Type `/whois @user` (mention any Discord user)
3. The command should execute and show Twitch verification info (or "not verified")

## Still Having Issues?

If you've followed all steps and it still doesn't work:

1. **Check bot logs:**
```bash
# Docker
docker-compose -f docker/docker-compose.yml logs -f bot

# Local
# Check console output where you ran python src/main.py
```

2. **Verify bot is online:**
   - Check Discord - bot should show as online
   - Check bot user in a server or DM

3. **Test with error logging:**
   - The bot now has a global error handler for slash commands
   - Check logs for any errors when you try to use the command

4. **Try removing and re-adding:**
   - User Settings → Connections → Remove bot
   - Use User Install link again
   - Select "Use this app everywhere"

## Additional Resources

- [Discord User Apps Documentation](https://discord.com/developers/docs/tutorials/developing-a-user-installable-app)
- [Discord App Commands Documentation](https://discord.com/developers/docs/interactions/application-commands)
- [discord.py Documentation - App Commands](https://discordpy.readthedocs.io/en/stable/interactions/api.html)

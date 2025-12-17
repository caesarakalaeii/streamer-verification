# Discord Developer Portal Setup Guide

Complete configuration guide for setting up your Discord application to work with the Twitch verification bot.

## Step 1: Create Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Enter a name (e.g., "Twitch Verification" or your server name)
4. Accept Terms of Service
5. Click **"Create"**

## Step 2: Configure General Information

1. Go to **General Information** tab
2. **Copy the Application ID** → Save as `DISCORD_OAUTH_CLIENT_ID` in .env

### Set Linked Roles Verification URL (CRITICAL!)

3. Scroll down to **Linked Roles Verification URL**
4. Enter your public URL: `https://your-domain.com/linked-role`
   - For local testing: `http://localhost:8080/linked-role`
   - For production: Your actual domain (must be HTTPS in production)
5. Click **"Save Changes"**

**This is the URL Discord redirects users to when they click "Link" in their profile!**

## Step 3: Configure Bot

1. Go to **Bot** tab
2. Click **"Reset Token"** to generate a new token
3. **Copy the bot token** → Save as `DISCORD_BOT_TOKEN` in .env
   - ⚠️ Keep this secret! Never commit to git or share publicly

### Enable Privileged Gateway Intents

4. Scroll down to **Privileged Gateway Intents**
5. Enable the following:
   - ✅ **Presence Intent** (optional, for online status)
   - ✅ **Server Members Intent** (REQUIRED - for member events and nickname management)
   - ✅ **Message Content Intent** (optional, not used by this bot)
6. Click **"Save Changes"**

### Bot Permissions Needed

The bot requires these permissions (set when generating invite link):
- **Manage Nicknames** - To set and enforce Twitch usernames
- **Manage Roles** - To assign verified role (though Discord does this automatically via Linked Roles)

## Step 4: Configure OAuth2

1. Go to **OAuth2 → General** tab

### Get Client Secret

2. Under **Client Information**:
   - **Client ID** is the same as Application ID (already saved)
   - Click **"Reset Secret"** to generate client secret
   - **Copy the client secret** → Save as `DISCORD_OAUTH_CLIENT_SECRET` in .env
   - ⚠️ Keep this secret! Never commit to git

### Add Redirect URIs

3. Scroll to **Redirects**
4. Click **"Add Redirect"**
5. Enter: `https://your-domain.com/linked-role`
   - For local testing: `http://localhost:8080/linked-role`
   - For production: Your actual domain (must be HTTPS)
6. Click **"Add Another"** if you want both local + production URLs
7. Click **"Save Changes"**

**Note:** The redirect URI must EXACTLY match what you set in:
- `DISCORD_OAUTH_REDIRECT_URI` in .env
- **Linked Roles Verification URL** in General Information

## Step 5: Generate Bot Invite Link

1. Go to **OAuth2 → URL Generator** tab
2. Select **Scopes**:
   - ✅ `bot` - Allows bot to join servers
   - ✅ `applications.commands` - Enables slash commands
3. Select **Bot Permissions**:
   - ✅ **Manage Nicknames** - Required for nickname enforcement
   - ✅ **Manage Roles** - Recommended (though Linked Roles handles role assignment)
4. **Copy the generated URL** at the bottom
5. Use this URL to invite the bot to your servers

## Step 6: Test Linked Roles (Optional)

1. Go to **General Information** tab
2. Under **Linked Roles Verification URL**, you'll see a **"Test"** button
3. Click it to test the OAuth flow yourself
4. This helps verify your URL is accessible and working

## Complete Environment Variables

After completing all steps, your `.env` should have:

```bash
# From Step 2 & 3
DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DISCORD_OAUTH_CLIENT_ID=YOUR_APPLICATION_ID_HERE
DISCORD_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE

# From Step 4 (must match redirect URI you added)
DISCORD_OAUTH_REDIRECT_URI=https://your-domain.com/linked-role
DISCORD_LINKED_ROLE_VERIFICATION_URL=https://your-domain.com/linked-role
```

## Verification Checklist

Before deploying, verify:

- [ ] Application created
- [ ] Application ID copied to `DISCORD_OAUTH_CLIENT_ID`
- [ ] Bot token generated and copied to `DISCORD_BOT_TOKEN`
- [ ] Client secret generated and copied to `DISCORD_OAUTH_CLIENT_SECRET`
- [ ] **Server Members Intent** enabled (REQUIRED!)
- [ ] Linked Roles Verification URL set to your domain + `/linked-role`
- [ ] OAuth2 redirect added (same URL as verification URL)
- [ ] Bot invite link generated with `bot` + `applications.commands` scopes
- [ ] Bot invite link includes "Manage Nicknames" permission

## Common Mistakes

### ❌ "Link" button doesn't appear in Discord Connections
**Solution:** You forgot to set the **Linked Roles Verification URL** in General Information tab

### ❌ OAuth error: redirect_uri mismatch
**Solution:** Your redirect URI in OAuth2 settings must EXACTLY match `DISCORD_OAUTH_REDIRECT_URI` in .env

### ❌ Bot can't change nicknames
**Solution:**
- Enable **Server Members Intent** in Bot tab
- Invite bot with **Manage Nicknames** permission
- Ensure bot's role is higher than users' roles in server role hierarchy

### ❌ Slash commands don't appear
**Solution:**
- Invite bot with `applications.commands` scope
- Wait up to 1 hour for Discord to sync global commands
- Re-invite bot if needed

## Testing Locally

For local development:

1. Use `http://localhost:8080/linked-role` as your URLs
2. Discord allows HTTP for localhost (otherwise requires HTTPS)
3. Set `.env`:
   ```bash
   DISCORD_OAUTH_REDIRECT_URI=http://localhost:8080/linked-role
   DISCORD_LINKED_ROLE_VERIFICATION_URL=http://localhost:8080/linked-role
   WEB_BASE_URL=http://localhost:8080
   ```
4. Use ngrok or similar if you need to test from Discord mobile/web

## Production Deployment

For production:

1. Get a domain with SSL certificate
2. Set up reverse proxy (nginx, Caddy, etc.)
3. Point to your bot's port (default 8080)
4. Update Discord Developer Portal with HTTPS URLs
5. Update `.env` with production URLs
6. **Important:** Must use HTTPS in production (Discord requirement)

## Next Steps

After Discord is configured:
1. Set up Twitch application (see TWITCH_SETUP.md if you create one, or README.md)
2. Deploy the bot
3. Invite bot to your server
4. Run `/setup` command
5. Tell users to verify!

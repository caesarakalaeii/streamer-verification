# Impersonation Detection Setup (Discord Server Owners)

Use this guide to enable the deployed impersonation detection bot in **your**
server. No coding or self-hosting is required—just install the bot, configure a
few commands, and you’re ready to catch Twitch impersonators automatically.

## 1. Install the Bot

1. Open this invite link:
   https://discord.com/oauth2/authorize?client_id=1450803650707587193
2. Choose your server and authorize the requested permissions (Manage Roles,
   Manage Nicknames, View Audit Log, etc.).
3. Confirm the bot appears online in your server.

> Tip: Only users with the “Manage Server” permission can add bots.

## 2. Prepare Your Server

Before running the setup command, make sure you have:

| Item | Purpose |
|------|---------|
| **Moderation channel** | Where impersonation alerts should be posted (text channel visible to staff). |
| **Quarantine role (optional)** | Role to assign automatically to suspicious users. Remove message/reaction permissions. |
| **Trusted roles list** | Roles that should bypass detection (e.g. Discord’s built-in `Twitch` role, manually verified streamers). |

## 3. Initial Setup (`/impersonation-setup`)

Run the command once per server (requires “Administrator” permission):

```
/impersonation-setup \
  enabled:true \
  moderation_channel:#mod-chat \
  min_score:70 \
  auto_quarantine:true \
  quarantine_role:@Quarantine \
  auto_dm:true \
  trusted_roles:@Twitch,@Partner
```

Field overview:

- `enabled` – Master switch for the feature.
- `moderation_channel` – Channel receiving rich alert embeds with action buttons.
- `min_score` – Minimum risk score needed before alerts fire (40–100).
- `auto_quarantine` / `quarantine_role` – Optional automatic containment.
- `auto_dm` – Sends a DM with verification instructions to flagged users.
- `trusted_roles` – Comma-separated roles that mark members as “already verified”.

## 4. Tune Settings (`/impersonation-config`)

Need to change thresholds later? Use the config command:

```
/impersonation-config min_score:65
/impersonation-config trusted_roles:@Twitch,@VIP
```

You can adjust any single field (channel, auto-quarantine, DM behavior, etc.)
without rerunning the full setup.

## 5. Handling Alerts

When the bot detects a suspicious account:

1. It posts an embed in your moderation channel showing similarity scores,
   account age, and Twitch info.
2. Moderators can click the action buttons (quarantine, whitelist, dismiss) or
   use slash commands for manual control.
3. The bot stores results so you can review them later.

Useful commands:

| Command | Description |
|---------|-------------|
| `/impersonation-review status:pending limit:25` | Shows recent detections awaiting review. |
| `/impersonation-details user:@suspect` | Detailed breakdown of a single detection. |
| `/impersonation-whitelist action:add user:@legit reason:"Verified"` | Suppress future alerts for a known good user. |
| `/impersonation-cache-refresh` | Reload cached Twitch info (max 100 entries per run). |

## 6. Best Practices

- **Trusted roles:** Add Discord’s built-in `Twitch` role or any other verified
  role so real streamers are never flagged.
- **Moderation workflow:** Pin the alert embeds in your mod channel or route
  them to a private staff category for easy access.
- **Educate staff:** Share this guide with moderators so they know how to react
  to alerts and mark false positives using `/impersonation-whitelist`.
- **Webhook logging (optional):** Create a dedicated logging channel if you want
  a permanent audit trail separate from the main moderation chat.

## 7. Troubleshooting

- **No alerts:** Run `/impersonation-config` to confirm `enabled:true` and that
  `min_score` isn’t set too high (start with 60–70).
- **Too many alerts:** Raise `min_score`, add more trusted roles, or whitelist
  recurring community members.
- **“Bot lacks permissions” message:** Ensure the bot’s role is above the
  quarantine/verified roles and has the required Discord permissions.

### Need More Detail?
- [Impersonation Detection System](IMPERSONATION_DETECTION.md): scoring,
  algorithm internals, cache design.
- [README](README.md): overall bot features and verification flow.

You’re all set! Once `/impersonation-setup` completes, the bot will begin
monitoring every new member (and daily batches) for suspicious Twitch lookalikes
with zero additional maintenance.

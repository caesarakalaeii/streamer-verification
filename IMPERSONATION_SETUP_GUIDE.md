# Impersonation Detection Setup Guide

This guide walks you through enabling the new impersonation detection system in
your production deployment. It assumes you already have the verification bot
running and connected to PostgreSQL.

## 1. Prerequisites

1. **Database migration** – run `python scripts/init_db.py` (or apply
   `src/database/migrations/002_pg_trgm_extension.sql`) with a privileged
   account. This enables the `pg_trgm` extension and creates the trigram index
   used for similarity searches.
2. **Bot version** – deploy `main` (or any build containing commit
   `c92d536` or newer). Older images do not include the optimized lookup path.
3. **Permissions** – ensure the bot has `Manage Roles`, `Manage Nicknames`, and
   `View Audit Log` if you plan to auto-quarantine or auto-update nicknames.

## 2. Discord Server Preparation

| Resource | Purpose | Notes |
|----------|---------|-------|
| Moderation channel | Receives alert embeds | Discord text channel visible to moderators only |
| Quarantine role *(optional)* | Auto-quarantine action target | Remove send/reaction permissions |
| Trusted roles *(optional)* | Exempt known verified users | e.g. Discord-native `Twitch` role |

## 3. Initial Configuration (`/impersonation-setup`)

Run the slash command once per guild as an administrator:

```
/impersonation-setup \
  enabled:true \
  moderation_channel:#moderation \
  min_score:70 \
  auto_quarantine:true \
  quarantine_role:@Quarantine \
  auto_dm:true \
  trusted_roles:@Twitch,@Partner
```

Key fields:

- `enabled` – master switch for the detector
- `moderation_channel` – where alerts appear
- `min_score` – minimum risk score (40–100) required before alerts are created
- `auto_quarantine` / `quarantine_role` – optional automatic containment
- `auto_dm` – send instructions to flagged users
- `trusted_roles` – comma-separated list of roles that should bypass detection

## 4. Ongoing Configuration (`/impersonation-config`)

Use `/impersonation-config` to tweak individual settings without running the
full setup again. Examples:

```
/impersonation-config min_score:60
/impersonation-config trusted_roles:@Twitch,@VIP
```

## 5. Streamer Cache Management

- **Auto-populate** – the service fetches likely Twitch profiles whenever it
  cannot find a match in the cache. It uses rate-limited semaphore control to
  avoid hitting Twitch limits.
- **Manual refresh** – `/impersonation-cache-refresh` updates cached entries.
- **Database health** – ensure `pg_trgm` stays enabled and the bot user owns the
  `streamer_cache` tables/indexes so startup migrations succeed.

## 6. Reviewing Detections

| Command | Purpose |
|---------|---------|
| `/impersonation-review status:pending limit:25` | List newest detections |
| `/impersonation-details user:@suspect` | Detailed breakdown + scores |
| `/impersonation-stats period:7d` | Aggregated metrics |
| `/impersonation-whitelist action:add user:@legit reason:"Manual verify"` | Suppress future alerts |

Moderators can take action from the alert embed (buttons) or manually assign
roles/kick users as needed.

## 7. Troubleshooting

- **No alerts** – confirm `/impersonation-config enabled:true` and that the
  minimum score is ≤ 80.
- **Database errors on startup** – ensure the bot user owns
  `streamer_cache`/`impersonation_*` tables and can run the migrations.
- **High log volume** – check `src/services/impersonation_detection_service`
  for warnings; common causes are missing trusted roles or Twitch rate limits.

Need more detail? See `IMPERSONATION_DETECTION.md` for the scoring model and
architecture, or `IMPERSONATION_DETECTION.md` → *Handling Strategies* for alert
automation ideas.

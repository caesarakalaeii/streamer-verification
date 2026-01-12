# Impersonation Detection System

## Overview

The impersonation detection system identifies Discord users who may be impersonating Twitch streamers by analyzing username similarity, account age, bio matching, and other behavioral patterns.

## Key Principle: Verified Users Are Trusted

### Primary Filter: Verification Status

**Impersonators never have Twitch accounts linked** - either through our bot's verification system or Discord's native connections. This is the most reliable indicator.

**Implementation:**
- ✅ **Verified users are automatically skipped** (our bot verification)
- ✅ **Trusted role users are automatically skipped** (Discord native verification or other bots)
- ✅ Users with verified Twitch connections are considered legitimate
- ✅ Only unverified users without trusted roles are analyzed

**Multi-Layer Trust System:**

1. **Layer 1: Our Bot Verification** (Primary)
   - Users who verified through `/verify` command
   - Checked in `tasks.py:358-365` and `events.py:87`
   - Strongest signal - we control the verification

2. **Layer 2: Trusted Roles** (Secondary)
   - Roles marked as "trusted" by server admins
   - Common use: Discord's native "Twitch" connection role
   - Checked in `impersonation_detection_service.py:60-70`
   - Flexible - works with any verification method

3. **Layer 3: Whitelist** (Manual Override)
   - Users manually marked as false positives
   - Checked in `impersonation_detection_service.py:49-57`
   - Final safety net

**Code Locations:**
- `src/bot/tasks.py:358-365` - Daily check skips verified users
- `src/bot/events.py:87` - Member join check only runs for unverified users
- `src/services/impersonation_detection_service.py:60-70` - Checks trusted roles
- `src/services/impersonation_detection_service.py:49-57` - Checks whitelist

### Why This Works

1. **Real streamers verify** - Legitimate streamers link their Twitch accounts (via our bot or Discord native)
2. **Impersonators can't verify** - They don't have access to the streamer's Twitch account
3. **Multiple trust paths** - Works with Discord native connections, other bots, or our verification
4. **Zero false positives** - We never flag someone who has proven Twitch ownership

### Trusted Roles Use Cases

**Example 1: Discord Native Twitch Connection**
If your server uses Discord's Connections feature with a "Twitch Verified" role:
```
/impersonation-setup trusted_roles: @Twitch
```
Users with `@Twitch` role = have Twitch connected via Discord = trusted

**Example 2: Multiple Verification Methods**
If your server has multiple verification bots or methods:
```
/impersonation-setup trusted_roles: @Twitch, @OtherBotVerified, @ManuallyVerified
```

**Example 3: Partner/VIP Roles**
Trust established community members:
```
/impersonation-setup trusted_roles: @Partner, @VIP, @Twitch
```

## Detection Algorithm

### Multi-Algorithm Similarity Detection

**Weighted Combination (0-100 scale):**
- **50%** - Levenshtein Distance (character edits)
- **30%** - Jaro-Winkler Similarity (transpositions, prefix matching)
- **20%** - Custom Pattern Detection (see below)

### Custom Pattern Detection

Detects common impersonation tactics:

```
Example Patterns:
- Adding numbers: "hiswattson247" → "hiswattson2470923"
- Adding underscores: "hiswattson247" → "hiswattson_247"
- Character substitution: "moonxi" → "m00nxi", "moonxl"
- Removing characters: "hiswattson247" → "hiswattson24"
```

### Scoring Components (0-100 Total)

| Component | Max Points | Description |
|-----------|-----------|-------------|
| **Username Similarity** | 40 | How similar is the Discord username to the streamer? |
| **Account Age** | 20 | How new is the Discord account? (1-7 days = highest risk) |
| **Bio Match** | 20 | Does the Discord bio match the streamer's Twitch bio? |
| **Streamer Popularity** | 10 | Is the streamer in the target range (1k-50k followers)? |
| **Discord Server Absence** | 10 | Does the streamer lack a Discord link on Twitch? |

### Risk Levels

- **Critical (80-100)**: Immediate alert, very high confidence
- **High (60-79)**: Alert for review, high confidence
- **Medium (40-59)**: Log and monitor, moderate suspicion
- **Low (0-39)**: Log only, unlikely impersonation

## Streamer Cache

### Purpose
Minimize Twitch API calls while maintaining fresh data for accurate detection.

### Data Cached
- Username and display name
- Follower count
- Bio/description
- Profile image URL
- Discord server link presence

### Cache Strategy
- **Initial Population**: Seeded from verified users in database
- **TTL**: 7 days for general data, 24 hours for follower/bio refresh
- **Refresh**: Automatic daily task + manual `/impersonation-cache-refresh`

### High-Scale Lookups
- Uses PostgreSQL's `pg_trgm` extension + GIN index to search by trigram
  similarity directly in the database
- Limits memory usage by streaming only the top ~50 closest usernames per
  Discord join event instead of loading the entire cache into Python
- Automatically falls back to length-based filtering if the extension is
  unavailable (e.g., during tests)

## Handling Strategies

Admins can enable strategies independently:

### 1. Alert Only (Default)
- Posts rich embed to moderation channel
- Shows interactive buttons for actions
- No automatic action taken

### 2. Auto-Quarantine
- Everything from Alert Only
- Automatically assigns quarantine role
- Removes posting/reaction permissions
- Moderators review when convenient

### 3. Auto-DM
- Everything from Alert Only
- Sends DM to user with verification instructions
- Explains how to prove legitimacy
- Directs to `/verify` command if they're the real streamer

## Admin Commands

### Setup & Configuration

```bash
# Initial setup
/impersonation-setup
  enabled: True
  moderation_channel: #moderation
  min_score: 70
  auto_quarantine: True
  quarantine_role: @Quarantine
  auto_dm: True
  trusted_roles: @Twitch, @Partner

# View current settings
/impersonation-config

# Update specific setting
/impersonation-config min_score: 60

# Add trusted roles
/impersonation-config trusted_roles: @TwitchVerified, @StreamerRole
```

### Review & Moderation

```bash
# List pending detections
/impersonation-review status: pending limit: 25

# View detailed info
/impersonation-details user: @suspicious_user

# View statistics
/impersonation-stats period: 7d
```

### Whitelist Management

```bash
# Add user (prevents future alerts)
/impersonation-whitelist action: add user: @legit_user reason: "Verified manually"

# Remove from whitelist
/impersonation-whitelist action: remove user: @user

# List all whitelisted users
/impersonation-whitelist action: list
```

### Maintenance

```bash
# Manually refresh streamer cache
/impersonation-cache-refresh
```

## Button Actions

When an alert is posted, moderators can click buttons:

- **🔨 Ban** - Ban user from server
- **👢 Kick** - Kick user from server
- **⚠️ Warn** - Send warning DM + log
- **✅ Mark Safe** - Mark as reviewed and safe
- **❌ False Positive** - Add to whitelist (prevents future alerts)

**Kubernetes-Safe:** Buttons work even after bot restarts!

## Verification Flow

### For Suspected Impersonators

If a user is flagged and receives a DM:

1. **Not impersonating?**
   - Contact server moderators
   - Consider changing username/avatar to avoid similarity
   - Wait for moderator review

2. **Are the actual streamer?**
   - Use `/verify` to link official Twitch account
   - This proves ownership and prevents future flags
   - Verification is permanent

### For Moderators

When reviewing detections:

1. Check alert embed for risk level and indicators
2. Review user's profile, join date, and behavior
3. Take action via buttons or let auto-strategies handle it
4. Add to whitelist if false positive

## Performance & Scale

### Large Guild Optimization
- Batch processing: 50 members per batch
- 5-second delays between batches
- Estimated time for 1,000 members: ~100 seconds

### Rate Limiting
- Twitch API: 800 requests/minute limit
- Our usage: ~600 requests/minute max
- Exponential backoff on failures

### Database Optimization
- Indexed queries for fast lookups
- LRU cache for similarity calculations (10,000 entries)
- Efficient cache hit tracking

## Future Enhancements

### 1. Native Discord Connections Check (Recommended)

**Goal:** Check if user has Twitch connection via Discord's native integration

**Challenge:** Discord.py doesn't expose user connections without OAuth flow

**Possible Solutions:**
- **Option A:** Request `connections` scope during OAuth flow (requires user consent)
- **Option B:** Check for Discord's native Twitch verified role (if server uses it)
- **Option C:** Use Discord API directly with bot token (limited access)

**Implementation Sketch:**
```python
# Pseudo-code for future implementation
async def has_native_twitch_connection(user_id: int) -> bool:
    """Check if user has Twitch connected to Discord."""
    # This would require additional OAuth scopes or API access
    # Currently not implemented - returns False
    return False

# Add to scoring:
if not has_native_twitch_connection(member.id):
    unverified_score += 15  # Add points for no Twitch connection
```

### 2. Cross-Server Detection Sharing

Share detection data between servers (with consent) to identify persistent impersonators.

### 3. Machine Learning Scoring

Train a model on moderator actions to improve scoring accuracy over time.

### 4. Appeal System

Allow flagged users to submit appeals via bot DMs with evidence.

## Troubleshooting

### No Alerts Appearing

1. Check detection is enabled: `/impersonation-config`
2. Verify moderation channel is set
3. Check bot permissions in moderation channel
4. Review logs for errors

### Too Many False Positives

1. Increase min_score threshold: `/impersonation-config min_score: 75`
2. Add legitimate users to whitelist
3. Review streamer cache for incorrect data

### Buttons Not Working After Restart

This shouldn't happen - buttons are persistent. If it does:
1. Check logs for errors during bot startup
2. Verify persistent view registration in `client.py`
3. Ensure database connection is healthy

## Security Considerations

- ✅ All commands require administrator permission
- ✅ Audit trail for all moderation actions
- ✅ Private moderator notes not visible to users
- ✅ Whitelist prevents repeated false alerts
- ✅ Rate limiting prevents API abuse

## Support

For issues or questions:
1. Check logs in your Kubernetes pod
2. Review this documentation
3. File issues at your repository

---

**Version:** 1.0
**Last Updated:** 2026-01-12
**Status:** Production Ready

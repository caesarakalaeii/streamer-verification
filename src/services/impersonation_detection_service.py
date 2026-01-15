"""Impersonation detection service for identifying potential streamer impersonators."""

import asyncio
import io
import logging
import re
from datetime import datetime, timezone
from typing import TypedDict

import discord
import httpx
import Levenshtein
from PIL import Image
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import GuildConfig, StreamerCache
from src.database.repositories import (
    ImpersonationDetectionRepository,
    ImpersonationWhitelistRepository,
    StreamerCacheRepository,
)
from src.services.rate_limiter import twitch_rate_limiter
from src.services.twitch_service import twitch_service
from src.shared.exceptions import TwitchAPIError

logger = logging.getLogger(__name__)


class ScoreDict(TypedDict):
    """Type definition for score dictionary."""

    total_score: int
    username_similarity_score: int
    account_age_score: int
    bio_match_score: int
    streamer_popularity_score: int
    discord_absence_score: int
    avatar_match_score: int
    risk_level: str


class ImpersonationDetectionService:
    """Service for detecting potential impersonation attempts."""

    def __init__(self):
        """Initialize the service with caching."""
        self.min_similarity_threshold = 65.0  # Only check if >65% similar
        self.avatar_similarity_threshold = 85.0  # Only compare avatars above this
        self._similarity_cache: dict[tuple[str, str], float] = (
            {}
        )  # Manual cache to avoid lru_cache memory leak
        self._avatar_hash_cache: dict[str, int] = {}
        self._avatar_hash_cache_limit = 2000
        self._auto_populate_semaphore = asyncio.Semaphore(
            5
        )  # Max 5 concurrent auto-populate operations

    async def check_user(
        self,
        db_session: AsyncSession,
        member: discord.Member,
        guild_id: int,
        guild_config: GuildConfig,
        trigger: str = "unknown",
    ) -> dict | None:
        """
        Check a user for potential impersonation.

        Returns a dict with detection details if suspicious, None otherwise.

        Note: This should only be called for unverified users. Verified users
        are legitimate and should be skipped before calling this method.
        """
        try:
            # Check if user is whitelisted
            is_whitelisted = await ImpersonationWhitelistRepository.is_whitelisted(
                db_session, member.id, guild_id
            )
            if is_whitelisted:
                logger.debug(
                    f"User {member.id} is whitelisted in guild {guild_id}, "
                    "skipping check"
                )
                return None

            # Check if user has trusted role (e.g., Discord's native Twitch
            # verification)
            if guild_config.impersonation_trusted_role_ids:
                trusted_role_ids = [
                    int(rid)
                    for rid in guild_config.impersonation_trusted_role_ids.split(",")
                    if rid.strip()
                ]
                if any(role.id in trusted_role_ids for role in member.roles):
                    logger.debug(
                        f"User {member.id} has trusted role in guild {guild_id}, "
                        "skipping check"
                    )
                    return None

            # Get user's Discord account age in days
            account_age_days = self._calculate_account_age_days(member.created_at)

            # Get user's bio (if available from member profile)
            discord_bio = None
            if hasattr(member, "bio") and member.bio:
                discord_bio = member.bio

            # Fetch only the most relevant cached streamers from the database
            cached_streamers = await StreamerCacheRepository.search_by_similarity(
                db_session, member.name
            )

            # Find the best match among cached streamers
            best_match: dict | None = None
            best_score = 0

            # First pass: check existing cache
            for cached_streamer in cached_streamers:
                # Calculate username similarity
                similarity = self._calculate_username_similarity(
                    member.name, cached_streamer.twitch_username
                )

                # Skip if similarity is below threshold
                if similarity < self.min_similarity_threshold:
                    continue

                # Calculate bio similarity if both bios exist
                bio_similarity = 0.0
                if discord_bio and cached_streamer.description:
                    bio_similarity = fuzz.ratio(
                        discord_bio.lower(), cached_streamer.description.lower()
                    )

                # Calculate total score
                candidate_scores = self._calculate_score(
                    username_similarity=similarity,
                    account_age_days=account_age_days,
                    bio_similarity=bio_similarity,
                    follower_count=cached_streamer.follower_count,
                    has_discord_link=cached_streamer.has_discord_link,
                )

                # Keep track of best match
                if candidate_scores["total_score"] > best_score:
                    best_score = candidate_scores["total_score"]
                    best_match = {
                        "streamer": cached_streamer,
                        "similarity": similarity,
                        "bio_similarity": bio_similarity,
                        "scores": candidate_scores,
                    }

            # Auto-populate cache if no good match found
            # This happens when cache is empty or user resembles an uncached streamer
            if best_score < self.min_similarity_threshold or not best_match:
                # Log current rate limit usage
                current, maximum = twitch_rate_limiter.get_current_usage()
                logger.info(
                    "No strong match in cache for %s (score: %s), "
                    "auto-populating from Twitch API (rate limit: %s/%s)",
                    member.name,
                    best_score,
                    current,
                    maximum,
                )

                # Use semaphore to limit concurrent auto-populate operations
                # This prevents overwhelming the API during mass scans
                async with self._auto_populate_semaphore:
                    # Search Twitch and add results to cache
                    added_count = await self._auto_populate_cache(
                        db_session, member.name
                    )

                if added_count > 0:
                    # Re-fetch targeted candidates with the expanded cache
                    cached_streamers = (
                        await StreamerCacheRepository.search_by_similarity(
                            db_session, member.name
                        )
                    )

                    # Second pass: check expanded cache
                    for cached_streamer in cached_streamers:
                        similarity = self._calculate_username_similarity(
                            member.name, cached_streamer.twitch_username
                        )

                        if similarity < self.min_similarity_threshold:
                            continue

                        bio_similarity = 0.0
                        if discord_bio and cached_streamer.description:
                            bio_similarity = fuzz.ratio(
                                discord_bio.lower(), cached_streamer.description.lower()
                            )

                        candidate_scores = self._calculate_score(
                            username_similarity=similarity,
                            account_age_days=account_age_days,
                            bio_similarity=bio_similarity,
                            follower_count=cached_streamer.follower_count,
                            has_discord_link=cached_streamer.has_discord_link,
                        )

                        if candidate_scores["total_score"] > best_score:
                            best_score = candidate_scores["total_score"]
                            best_match = {
                                "streamer": cached_streamer,
                                "similarity": similarity,
                                "bio_similarity": bio_similarity,
                                "scores": candidate_scores,
                            }

                    logger.info(
                        "After auto-populate: best score %s for %s",
                        best_score,
                        member.name,
                    )

            if best_match is None:
                logger.debug(
                    f"User {member.id} has no matching streamer candidates, skipping"
                )
                return None

            matched_streamer: StreamerCache = best_match["streamer"]  # type: ignore[assignment]
            matched_scores: ScoreDict = best_match["scores"]  # type: ignore[assignment]

            # Optional avatar comparison (only for strong username matches)
            avatar_similarity = 0.0
            if (
                best_match["similarity"] >= self.avatar_similarity_threshold
                and matched_streamer.profile_image_hash is not None
                and self._is_custom_avatar(member)
            ):
                avatar_url = member.display_avatar.with_size(128).url
                discord_hash = await self._get_avatar_hash(avatar_url)
                if discord_hash is not None:
                    avatar_similarity = self._calculate_avatar_similarity(
                        discord_hash, matched_streamer.profile_image_hash
                    )

            if avatar_similarity > 0:
                matched_scores = self._calculate_score(
                    username_similarity=best_match["similarity"],
                    account_age_days=account_age_days,
                    bio_similarity=best_match["bio_similarity"],
                    follower_count=matched_streamer.follower_count,
                    has_discord_link=matched_streamer.has_discord_link,
                    avatar_similarity=avatar_similarity,
                )
                best_score = matched_scores["total_score"]

            # If best score is below 40, not suspicious enough to report
            if best_score < 40 or best_match is None:
                logger.debug(
                    "User %s best score %s below threshold, not suspicious",
                    member.id,
                    best_score,
                )
                return None

            # Create detection record

            detection = await ImpersonationDetectionRepository.create(
                db_session,
                guild_id=guild_id,
                discord_user_id=member.id,
                discord_username=member.name,
                discord_display_name=member.display_name,
                discord_account_age_days=account_age_days,
                discord_bio=discord_bio,
                suspected_streamer_id=matched_streamer.twitch_user_id,
                suspected_streamer_username=matched_streamer.twitch_username,
                suspected_streamer_follower_count=matched_streamer.follower_count,
                total_score=matched_scores["total_score"],
                username_similarity_score=matched_scores["username_similarity_score"],
                account_age_score=matched_scores["account_age_score"],
                bio_match_score=matched_scores["bio_match_score"],
                streamer_popularity_score=matched_scores["streamer_popularity_score"],
                discord_absence_score=matched_scores["discord_absence_score"],
                avatar_match_score=matched_scores["avatar_match_score"],
                risk_level=matched_scores["risk_level"],
                detection_trigger=trigger,
            )

            await db_session.commit()

            logger.info(
                "Detected potential impersonation: %s -> %s (score: %s, risk: %s)",
                member.name,
                matched_streamer.twitch_username,
                matched_scores["total_score"],
                matched_scores["risk_level"],
            )

            # Return detection details
            return {
                "detection": detection,
                "member": member,
                "streamer": matched_streamer,
                "similarity": best_match["similarity"],
                "bio_similarity": best_match["bio_similarity"],
                "scores": matched_scores,
            }

        except Exception as e:
            logger.error(
                f"Error checking user {member.id} for impersonation: {e}", exc_info=True
            )
            await db_session.rollback()
            return None

    @staticmethod
    def _calculate_account_age_days(
        created_at: datetime, current_time: datetime | None = None
    ) -> int:
        """Return account age in days, handling timezone-aware values."""

        reference_time = current_time or datetime.now(timezone.utc)

        normalized_created = created_at
        if created_at.tzinfo is None or created_at.tzinfo.utcoffset(created_at) is None:
            normalized_created = created_at.replace(tzinfo=timezone.utc)

        age_delta = reference_time - normalized_created
        return max(age_delta.days, 0)

    def _calculate_username_similarity(self, username1: str, username2: str) -> float:
        """
        Calculate username similarity using a hybrid algorithm.

        Returns a score from 0-100 representing similarity percentage.
        Uses weighted combination of:
        - Levenshtein distance (50% weight)
        - Jaro-Winkler similarity (30% weight)
        - Custom impersonation patterns (20% weight)
        """
        # Check cache first
        sorted_usernames = sorted([username1.lower(), username2.lower()])
        cache_key: tuple[str, str] = (sorted_usernames[0], sorted_usernames[1])
        if cache_key in self._similarity_cache:
            return self._similarity_cache[cache_key]

        # Normalize usernames
        norm1 = self._normalize_username(username1)
        norm2 = self._normalize_username(username2)

        # Handle edge cases
        if not norm1 or not norm2:
            return 0.0
        if norm1 == norm2:
            self._similarity_cache[cache_key] = 100.0
            return 100.0

        # Calculate Levenshtein similarity (50% weight)
        max_len = max(len(norm1), len(norm2))
        lev_distance = Levenshtein.distance(norm1, norm2)
        lev_similarity = (1 - (lev_distance / max_len)) * 100

        # Calculate Jaro-Winkler similarity (30% weight)
        jaro_similarity = float(fuzz.ratio(norm1, norm2))

        # Check custom impersonation patterns (20% weight)
        pattern_score = self._check_impersonation_patterns(username1, username2)

        # Weighted combination
        final_score = (
            (lev_similarity * 0.5) + (jaro_similarity * 0.3) + (pattern_score * 0.2)
        )

        result = float(round(final_score, 2))
        self._similarity_cache[cache_key] = result

        # Limit cache size to prevent memory bloat (keep last 10000 entries)
        if len(self._similarity_cache) > 10000:
            # Remove oldest entries (simple FIFO)
            for _ in range(1000):
                self._similarity_cache.pop(next(iter(self._similarity_cache)))

        return result

    def _normalize_username(self, username: str) -> str:
        """
        Normalize username for comparison.

        Removes special characters, converts to lowercase, removes trailing numbers.
        """
        if not username:
            return ""

        # Convert to lowercase
        normalized = username.lower()

        # Remove common special characters but keep letters and numbers
        normalized = re.sub(r"[_\-\s\.]", "", normalized)

        return normalized

    def _check_impersonation_patterns(self, username1: str, username2: str) -> float:
        """
        Check for common impersonation patterns.

        Returns a score from 0-100 based on detected patterns.
        """
        # Normalize for pattern checking
        norm1 = self._normalize_username(username1)
        norm2 = self._normalize_username(username2)

        score = 0.0

        # Pattern 1: Adding random numbers
        # Example: "hiswattson247" -> "hiswattson2470923"
        # Extract base (letters only)
        base1 = re.sub(r"\d+", "", norm1)
        base2 = re.sub(r"\d+", "", norm2)

        if base1 and base2 and base1 == base2:
            # Same base, different numbers = high suspicion
            score += 50.0

        # Pattern 2: Character substitution (o->0, i->1, l->1)
        substituted1 = norm1.replace("0", "o").replace("1", "il")
        substituted2 = norm2.replace("0", "o").replace("1", "il")

        if (
            substituted1 == substituted2
            or substituted1 in substituted2
            or substituted2 in substituted1
        ):
            score += 30.0

        # Pattern 3: One username contains the other
        if norm1 in norm2 or norm2 in norm1:
            # Calculate how much is added
            len_diff = abs(len(norm1) - len(norm2))
            if len_diff <= 5:  # Small addition (like "_247")
                score += 40.0
            elif len_diff <= 10:
                score += 20.0

        return min(score, 100.0)

    def _calculate_score(
        self,
        username_similarity: float,
        account_age_days: int,
        bio_similarity: float,
        follower_count: int,
        has_discord_link: bool,
        avatar_similarity: float = 0.0,
    ) -> ScoreDict:
        """
        Calculate component scores and total score.

        Returns dict with all score components and total.
        """
        # Username Similarity Score (0-40 points)
        if username_similarity >= 95:
            username_score = 40
        elif username_similarity >= 85:
            username_score = 30
        elif username_similarity >= 75:
            username_score = 20
        elif username_similarity >= 65:
            username_score = 10
        else:
            username_score = 0

        # Account Age Score (0-20 points)
        if account_age_days <= 7:
            age_score = 20
        elif account_age_days <= 30:
            age_score = 15
        elif account_age_days <= 90:
            age_score = 10
        elif account_age_days <= 180:
            age_score = 5
        elif account_age_days <= 365:
            age_score = 2
        else:
            age_score = 0

        # Bio Match Score (0-20 points)
        if bio_similarity >= 100:
            bio_score = 20
        elif bio_similarity >= 90:
            bio_score = 15
        elif bio_similarity >= 70:
            bio_score = 10
        elif bio_similarity >= 50:
            bio_score = 5
        else:
            bio_score = 0

        # Streamer Popularity Score (0-10 points)
        # Target range for impersonation: 1k-50k followers
        if 1000 <= follower_count <= 50000:
            popularity_score = 10
        elif (500 <= follower_count < 1000) or (50000 < follower_count <= 100000):
            popularity_score = 5
        elif (100 <= follower_count < 500) or (100000 < follower_count <= 500000):
            popularity_score = 2
        else:
            popularity_score = 0

        # Discord Server Absence Score (0-10 points)
        discord_score = 0 if has_discord_link else 10

        # Avatar Match Score (0-10 points)
        if avatar_similarity >= 90:
            avatar_score = 10
        elif avatar_similarity >= 80:
            avatar_score = 5
        else:
            avatar_score = 0

        # Calculate total
        total_score = (
            username_score
            + age_score
            + bio_score
            + popularity_score
            + discord_score
            + avatar_score
        )

        # Determine risk level
        if total_score >= 80:
            risk_level = "critical"
        elif total_score >= 60:
            risk_level = "high"
        elif total_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "total_score": total_score,
            "username_similarity_score": username_score,
            "account_age_score": age_score,
            "bio_match_score": bio_score,
            "streamer_popularity_score": popularity_score,
            "discord_absence_score": discord_score,
            "avatar_match_score": avatar_score,
            "risk_level": risk_level,
        }

    @staticmethod
    def _is_custom_avatar(member: discord.Member) -> bool:
        """Return True if the member has a custom avatar."""
        return member.avatar is not None or member.guild_avatar is not None

    async def _get_avatar_hash(self, url: str) -> int | None:
        """Fetch and hash an avatar image, with a small in-memory cache."""
        cached = self._avatar_hash_cache.get(url)
        if cached is not None:
            return cached

        image_bytes = await self._fetch_image_bytes(url)
        if not image_bytes:
            return None

        avatar_hash = self._compute_dhash(image_bytes)
        if avatar_hash is None:
            return None

        self._avatar_hash_cache[url] = avatar_hash
        if len(self._avatar_hash_cache) > self._avatar_hash_cache_limit:
            for _ in range(200):
                self._avatar_hash_cache.pop(next(iter(self._avatar_hash_cache)))

        return avatar_hash

    @staticmethod
    async def _fetch_image_bytes(url: str, max_bytes: int = 2_000_000) -> bytes | None:
        """Fetch image bytes with a size guard to avoid large downloads."""
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, timeout=5.0)
            if response.status_code != 200:
                return None
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        return None
                except ValueError:
                    pass
            if len(response.content) > max_bytes:
                return None
            if not response.headers.get("content-type", "").startswith("image/"):
                return None
            return response.content
        except Exception:
            return None

    @staticmethod
    def _compute_dhash(image_bytes: bytes) -> int | None:
        """Compute a 64-bit difference hash for an image."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                gray = image.convert("L")
                resized = gray.resize((9, 8), Image.Resampling.LANCZOS)
                pixels = list(resized.getdata())
        except Exception:
            return None

        hash_value = 0
        for row in range(8):
            row_start = row * 9
            for col in range(8):
                left = pixels[row_start + col]
                right = pixels[row_start + col + 1]
                hash_value = (hash_value << 1) | (1 if left > right else 0)

        return hash_value

    @staticmethod
    def _calculate_avatar_similarity(hash_a: int, hash_b: int) -> float:
        """Return similarity score (0-100) based on dHash Hamming distance."""
        distance = (hash_a ^ hash_b).bit_count()
        similarity = (1 - (distance / 64)) * 100
        return max(0.0, float(round(similarity, 2)))

    async def is_whitelisted(
        self, db_session: AsyncSession, user_id: int, guild_id: int
    ) -> bool:
        """Check if a user is whitelisted for a guild."""
        return await ImpersonationWhitelistRepository.is_whitelisted(
            db_session, user_id, guild_id
        )

    async def refresh_streamer_cache(
        self, db_session: AsyncSession, twitch_user_id: str
    ) -> bool:
        """
        Refresh a streamer's cached data from Twitch API.

        Returns True if successful, False if failed.
        """
        try:
            # Get user profile from Twitch
            profile = await twitch_service.get_user_profile(user_id=twitch_user_id)

            # Get follower count
            try:
                follower_count = await twitch_service.get_follower_count(twitch_user_id)
            except TwitchAPIError:
                logger.warning(
                    f"Failed to get follower count for {twitch_user_id}, using 0"
                )
                follower_count = 0

            # Check for Discord link
            description = profile.get("description", "")
            has_discord_link = twitch_service.has_discord_link(description)

            # Update or create cache entry
            existing = await StreamerCacheRepository.get_by_twitch_id(
                db_session, twitch_user_id
            )

            if existing:
                # Update existing
                profile_image_url = profile.get("profile_image_url")
                profile_image_hash = existing.profile_image_hash
                if profile_image_url and (
                    profile_image_url != existing.profile_image_url
                    or profile_image_hash is None
                ):
                    profile_image_hash = await self._get_avatar_hash(profile_image_url)

                await StreamerCacheRepository.update(
                    db_session,
                    twitch_user_id=twitch_user_id,
                    twitch_username=profile.get("login", ""),
                    twitch_display_name=profile.get("display_name"),
                    follower_count=follower_count,
                    description=description,
                    has_discord_link=has_discord_link,
                    profile_image_url=profile_image_url,
                    profile_image_hash=profile_image_hash,
                )
            else:
                # Create new
                profile_image_url = profile.get("profile_image_url")
                profile_image_hash = None
                if profile_image_url:
                    profile_image_hash = await self._get_avatar_hash(profile_image_url)
                await StreamerCacheRepository.create(
                    db_session,
                    twitch_user_id=twitch_user_id,
                    twitch_username=profile.get("login", ""),
                    twitch_display_name=profile.get("display_name"),
                    follower_count=follower_count,
                    description=description,
                    has_discord_link=has_discord_link,
                    profile_image_url=profile_image_url,
                    profile_image_hash=profile_image_hash,
                )

            await db_session.commit()
            logger.info(
                "Refreshed cache for streamer %s (%s)",
                profile.get("login"),
                twitch_user_id,
            )
            return True

        except TwitchAPIError as e:
            logger.warning(f"Failed to refresh cache for {twitch_user_id}: {e}")
            await db_session.rollback()
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error refreshing cache for {twitch_user_id}: {e}",
                exc_info=True,
            )
            await db_session.rollback()
            return False

    async def _auto_populate_cache(
        self, db_session: AsyncSession, username: str
    ) -> int:
        """
        Auto-populate cache by searching Twitch API for similar streamers.

        Args:
            db_session: Database session
            username: Username to search for (typically a Discord username)

        Returns:
            Number of new streamers added to cache
        """
        try:
            # Normalize username for better search results
            search_query = self._normalize_username(username)

            # If normalized is too short, use original
            if len(search_query) < 3:
                search_query = username

            logger.info(
                f"Auto-populating cache by searching Twitch for '{search_query}'"
            )

            # Search Twitch for similar channels
            try:
                search_results = await twitch_service.search_channels(
                    query=search_query, limit=10
                )
            except TwitchAPIError as e:
                logger.warning(f"Twitch search failed for '{search_query}': {e}")
                return 0

            if not search_results:
                logger.debug(f"No Twitch channels found for '{search_query}'")
                return 0

            added_count = 0

            # Add each result to cache (with rate limiting)
            for i, result in enumerate(search_results):
                twitch_user_id = result.get("id")
                twitch_username = result.get("broadcaster_login")

                if not twitch_user_id or not twitch_username:
                    continue

                # Check if already in cache
                existing = await StreamerCacheRepository.get_by_twitch_id(
                    db_session, twitch_user_id
                )
                if existing:
                    # Increment cache hit counter
                    await StreamerCacheRepository.increment_cache_hits(
                        db_session, twitch_user_id
                    )
                    continue

                # Get full profile and follower count
                try:
                    profile = await twitch_service.get_user_profile(
                        user_id=twitch_user_id
                    )
                    follower_count = await twitch_service.get_follower_count(
                        twitch_user_id
                    )
                except TwitchAPIError as e:
                    logger.warning(
                        f"Failed to fetch profile for {twitch_username}: {e}"
                    )
                    # Use search result data as fallback
                    profile = result
                    follower_count = 0

                # Check for Discord link
                description = profile.get("description", "")
                has_discord_link = twitch_service.has_discord_link(description)

                # Add to cache
                try:
                    profile_image_url = profile.get("thumbnail_url") or profile.get(
                        "profile_image_url"
                    )
                    profile_image_hash = None
                    if profile_image_url:
                        profile_image_hash = await self._get_avatar_hash(
                            profile_image_url
                        )
                    await StreamerCacheRepository.create(
                        db_session,
                        twitch_user_id=twitch_user_id,
                        twitch_username=twitch_username,
                        twitch_display_name=profile.get("display_name"),
                        follower_count=follower_count,
                        description=description,
                        has_discord_link=has_discord_link,
                        profile_image_url=profile_image_url,
                        profile_image_hash=profile_image_hash,
                    )
                    added_count += 1
                    logger.info(
                        "Added %s to cache (followers: %s)",
                        twitch_username,
                        follower_count,
                    )
                except Exception as e:
                    logger.warning(f"Failed to add {twitch_username} to cache: {e}")
                    continue

                # Small delay between processing results to spread out API calls
                # This helps when multiple auto-populate operations run concurrently
                if i < len(search_results) - 1:  # Don't delay after last item
                    await asyncio.sleep(0.1)

            await db_session.commit()
            logger.info(
                "Auto-populated cache: added %s streamers from search '%s'",
                added_count,
                search_query,
            )
            return added_count

        except Exception as e:
            logger.error(f"Error in auto-populate cache: {e}", exc_info=True)
            await db_session.rollback()
            return 0


# Global service instance
impersonation_detection_service = ImpersonationDetectionService()

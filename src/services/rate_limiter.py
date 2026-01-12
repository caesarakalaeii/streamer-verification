"""Rate limiter for Twitch API to prevent hitting rate limits."""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class TwitchAPIRateLimiter:
    """
    Rate limiter for Twitch API requests.

    Twitch Helix API limits:
    - 800 requests per minute
    - OAuth: 50 requests per minute

    This limiter ensures we stay under the limit with safety margin.
    """

    def __init__(self, requests_per_minute: int = 600):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute (default: 600 for safety margin)
        """
        self.requests_per_minute = requests_per_minute
        self.request_times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """
        Wait until safe to make a request.

        Implements sliding window rate limiting to stay under Twitch API limits.
        """
        async with self._lock:
            now = time.time()

            # Remove requests older than 60 seconds (sliding window)
            while self.request_times and now - self.request_times[0] >= 60:
                self.request_times.popleft()

            # If at limit, wait until oldest request expires
            if len(self.request_times) >= self.requests_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    logger.debug(
                        f"Rate limit reached ({len(self.request_times)}/{self.requests_per_minute}), "
                        f"waiting {sleep_time:.1f}s"
                    )
                    await asyncio.sleep(sleep_time)

                    # Remove expired after sleep
                    now = time.time()
                    while self.request_times and now - self.request_times[0] >= 60:
                        self.request_times.popleft()

            # Record this request
            self.request_times.append(time.time())

    def get_current_usage(self) -> tuple[int, int]:
        """
        Get current rate limit usage.

        Returns:
            Tuple of (current_requests, max_requests)
        """
        now = time.time()

        # Count requests in last 60 seconds
        count = sum(1 for t in self.request_times if now - t < 60)

        return count, self.requests_per_minute


# Global rate limiter instance
twitch_rate_limiter = TwitchAPIRateLimiter(requests_per_minute=600)

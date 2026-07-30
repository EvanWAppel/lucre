"""Shared rate limiters guarding anonymous demo traffic (PRD H5).

Kept in their own module so the demo middleware and the test-reset fixture both
reference the same instances without importing the whole app.
"""

from rate_limit import SlidingWindowRateLimiter

# New demo sandboxes a single client IP may spin up per minute.
create_limiter = SlidingWindowRateLimiter(max_events=20, window_seconds=60)
# Write actions (POST/PATCH/DELETE) a single demo session may make per minute.
write_limiter = SlidingWindowRateLimiter(max_events=60, window_seconds=60)

import redis
import structlog


log = structlog.get_logger()

REQUESTS_PER_WINDOW = 10
WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.client = redis.Redis(host=host, port=port, decode_responses=True)

    def is_allowed(self, identifier: str) -> bool:
        key = f"ratelimit:{identifier}"

        # Atomic increment; if key doesn't exist, starts at 0 then becomes 1
        current = self.client.incr(key)

        if current == 1:
            # First request in this window — set expiry to start the clock
            self.client.expire(key, WINDOW_SECONDS)

        if current > REQUESTS_PER_WINDOW:
            log.info("rate_limit_exceeded", identifier=identifier, count=current)
            return False

        return True
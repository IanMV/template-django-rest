from itertools import batched

from django.core.cache.backends.redis import RedisCache


class TestRedisCache(RedisCache):
    def clear(self):
        self._delete_pattern("*")

    def clear_rate_limits(self):
        for prefix in ("code-request", "code-verify", "login", "reauth"):
            self._delete_pattern(f"{prefix}:*")

    def _delete_pattern(self, pattern):
        # Never flush a Redis database shared with unrelated local applications.
        assert self.key_prefix.startswith("template-auth-test:")
        client = self._cache.get_client(write=True)
        for keys in batched(client.scan_iter(match=self.make_key(pattern)), 500):
            client.delete(*keys)

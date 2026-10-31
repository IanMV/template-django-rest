from itertools import batched

from django.core.cache.backends.redis import RedisCache


class TestRedisCache(RedisCache):
    def clear(self):
        # Never flush a Redis database shared with unrelated local applications.
        assert self.key_prefix.startswith("template-auth-test:")
        client = self._cache.get_client(write=True)
        for keys in batched(client.scan_iter(match=self.make_key("*")), 500):
            client.delete(*keys)

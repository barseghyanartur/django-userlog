import datetime
from collections import namedtuple
import json

import redis

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured
from django.dispatch import receiver
from django.test.signals import setting_changed
from django.utils.timezone import utc


_client = None      # Cached instance of the Redis client.

_settings = None    # Cached dict of userlog settings


@receiver(setting_changed)
def reset_caches(**kwargs):
    global _client, _settings
    if kwargs['setting'] == 'CACHES':
        _client = None
        _settings = None


def get_redis_client():
    global _client

    if _client is not None:
        return _client

    try:
        cache = caches['userlog']
    except KeyError:
        raise ImproperlyConfigured("No 'userlog' cache found in CACHES.")

    try:
        try:
            _client = cache.client      # django-redis
        except AttributeError:
            _client = cache._client     # django-redis-cache
        assert isinstance(_client, redis.StrictRedis)
    except (AssertionError, AttributeError):
        raise ImproperlyConfigured("'userlog' cache doesn't use Redis.")

    return _client


def convert_timestamp(ts):
    if settings.USE_TZ:
        return datetime.datetime.utcfromtimestamp(ts).replace(tzinfo=utc)
    else:
        return datetime.datetime.fromtimestamp(ts)


def get_log(username):
    """
    Return a list of page views.

    Each item is a dict with `datetime`, `method`, `path` and `code` keys.
    """
    redis = get_redis_client()
    log_key = 'log:{}'.format(username)
    raw_log = redis.lrange(log_key, 0, -1)
    log = []
    for raw_item in raw_log:
        item = json.loads(raw_item.decode())
        item['datetime'] = convert_timestamp(item.pop('time'))
        log.append(item)
    return log


UserLogSettings = namedtuple('UserLogSettings', ['timeout', 'max_size'])


def get_userlog_settings():
    global _settings

    if _settings is not None:
        return _settings

    userlog = settings.CACHES['userlog']
    options = userlog.get('OPTIONS', {})

    # Coerce values into expected types in order to detect invalid settings.
    _settings = UserLogSettings(
        # Hardcode the default value because it isn't exposed by Django.
        timeout=int(userlog.get('TIMEOUT', 300)),
        max_size=int(options.get('MAX_SIZE', 25)),
    )

    return _settings
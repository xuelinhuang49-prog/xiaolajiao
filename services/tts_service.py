# -*- coding: utf-8 -*-
"""小辣椒 TTS：保留原调用接口，增加有界内存缓存、并发请求合并与耗时日志。"""
import asyncio
import hashlib
import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future

import edge_tts

DEFAULT_VOICE = 'zh-CN-shaanxi-XiaoniNeural'
_MAX_CACHE_ENTRIES = 96
_MAX_CACHE_BYTES = 16 * 1024 * 1024
_MAX_ITEM_BYTES = 512 * 1024
_cache = OrderedDict()
_cache_bytes = 0
_inflight = {}
_lock = threading.Lock()
_log = logging.getLogger('xiaolajiao.tts')
if not _log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('[小辣椒TTS] %(message)s'))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False


async def synthesize(text: str, voice: str, rate: str = '+0%') -> bytes:
    """兼容旧版异步接口。"""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    chunks = []
    async for chunk in communicate.stream():
        if chunk['type'] == 'audio':
            chunks.append(chunk['data'])
    result = b''.join(chunks)
    if not result:
        raise RuntimeError('Edge TTS 未返回音频数据')
    return result


def synthesize_sync(text: str, voice: str, rate: str = '+0%') -> bytes:
    """同步接口，与原 server.py 完全兼容；相同文本、音色、语速命中缓存。"""
    global _cache_bytes
    key = (text, voice, rate)
    label = hashlib.sha256(repr(key).encode('utf-8')).hexdigest()[:10]
    start = time.perf_counter()
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            _log.info('cache_hit key=%s chars=%d ms=%.1f', label, len(text), (time.perf_counter()-start)*1000)
            return cached
        future = _inflight.get(key)
        if future is None:
            future = Future()
            _inflight[key] = future
            owner = True
        else:
            owner = False
    if not owner:
        result = future.result()  # 同一音频只合成一次；异常原样传播
        _log.info('shared_result key=%s chars=%d ms=%.1f', label, len(text), (time.perf_counter()-start)*1000)
        return result
    try:
        result = asyncio.run(synthesize(text, voice, rate))
        with _lock:
            if len(result) <= _MAX_ITEM_BYTES:
                while _cache and (len(_cache) >= _MAX_CACHE_ENTRIES or _cache_bytes + len(result) > _MAX_CACHE_BYTES):
                    _, removed = _cache.popitem(last=False)
                    _cache_bytes -= len(removed)
                _cache[key] = result
                _cache_bytes += len(result)
            future.set_result(result)
            del _inflight[key]
        _log.info('generated key=%s chars=%d bytes=%d ms=%.1f', label, len(text), len(result), (time.perf_counter()-start)*1000)
        return result
    except BaseException as exc:
        with _lock:
            future.set_exception(exc)
            del _inflight[key]
        _log.warning('failed key=%s chars=%d ms=%.1f error=%s', label, len(text), (time.perf_counter()-start)*1000, type(exc).__name__)
        raise

# -*- coding: utf-8 -*-
"""通用任务状态管理：阶段常量 + 肯定/否定判断 + 内存会话注册表。

每个业务功能（购物、提醒……）复用同一套会话管理，新增功能时照搬即可。
"""
import re
import time

# 任务阶段
ASK_ITEM = 'ask_item'
ASK_QUANTITY = 'ask_quantity'
CONFIRM = 'confirm'
DONE = 'done'
CANCELLED = 'cancelled'


def is_affirm(text: str) -> bool:
    return bool(re.match(
        r'^(好|好的|行|可以|能|是|对|要|打|确认|下单|买|来|成|嗯|ok|要得|中|对呀|好呀)',
        (text or '').strip(), re.I))


def is_negate(text: str) -> bool:
    s = (text or '').strip()
    if re.match(r'^(不|不了|不用|不要|别|算了|取消)$', s):
        return True
    return bool(re.search(r'(算了|取消|别买了|别打了|不买了|不打了|不要了|不用了)', s))


class Sessions:
    """极简内存会话注册表（单用户演示足够），按空闲超时清理。"""

    def __init__(self, idle_seconds=600):
        self._store = {}
        self._idle_seconds = idle_seconds

    def get_or_create(self, session_id, factory):
        self._gc()
        item = self._store.get(session_id)
        if item is None:
            item = {'obj': factory(), 'ts': time.time()}
            self._store[session_id] = item
        else:
            item['ts'] = time.time()
        return item['obj']

    def drop(self, session_id):
        self._store.pop(session_id, None)

    def _gc(self):
        now = time.time()
        stale = [k for k, v in self._store.items() if now - v['ts'] > self._idle_seconds]
        for k in stale:
            self._store.pop(k, None)

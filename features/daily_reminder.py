# -*- coding: utf-8 -*-
"""日常提醒：解析“明天早上八点提醒我出门”，新增 / 查看 / 取消，到点通知。

会话状态机（复用 task_manager 的肯定/否定判断）：
  解析时间+内容 → 缺时间问时间 / 缺内容问内容 → 确认 → 记下。
提醒持久化到本地 JSON；到点由前端轮询 /api/reminder/check 触发通知。
"""
import re
import json
import os
from pathlib import Path
import threading
import uuid
from datetime import datetime, timedelta

from features.task_manager import DONE, CANCELLED, is_affirm, is_negate

# 中文数字 → 阿拉伯数字
_NUM = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
_DAY = {'今天': 0, '明天': 1, '后天': 2, '大后天': 3}

_TIME_RE = re.compile(
    r'(凌晨|早上|早晨|上午|中午|下午|晚上|夜里)?\s*'
    r'([零一二两三四五六七八九十百\d]+)\s*[点時时]\s*(半)?\s*'
    r'([零一二两三四五六七八九十\d]+)?\s*(分)?')

# 相对时间："60秒后 / 一分钟后 / 半小时后"
_REL_RE = re.compile(r'([零一二两三四五六七八九十\d]+)\s*(秒钟|分钟|小时|钟头|秒|分)\s*(?:后|以后)')
_REL_SECS = {'秒': 1, '秒钟': 1, '分': 60, '分钟': 60, '小时': 3600, '钟头': 3600}


def _cn_int(s):
    if s is None:
        return None
    s = s.strip()
    if s in _NUM:
        return _NUM[s]
    if s.isdigit():
        return int(s)
    if '十' in s:
        a, _, b = s.partition('十')
        tens = _NUM.get(a, 1) if a else 1
        ones = _NUM.get(b, 0) if b else 0
        return tens * 10 + ones
    return None


def _period_shift(period, hour):
    """把“下午三点”换算成 24 小时制的 15 点。"""
    if period in ('中午', '下午', '晚上', '夜里'):
        return hour + 12 if hour < 12 else hour
    return hour


def parse_reminder(text, now=None):
    """返回 (when: datetime|None, content: str)。没识别到时间则 when=None。"""
    now = now or datetime.now()
    day_offset = 0
    m = re.search(r'(今天|明天|后天|大后天)', text)
    if m:
        day_offset = _DAY[m.group(1)]

    tm = _TIME_RE.search(text)
    hour = minute = None
    if tm:
        period = tm.group(1) or ''
        hour = _cn_int(tm.group(2))
        if tm.group(3):           # “半”
            minute = 30
        if tm.group(4):
            minute = _cn_int(tm.group(4)) or 0
        if minute is None:
            minute = 0
        if hour is not None:
            hour = _period_shift(period, hour)

    when = None
    # 相对时间："60秒后 / 一分钟后 / 半小时后"（便于现场演示到点通知）
    rel_m = _REL_RE.search(text)
    if rel_m:
        n = _cn_int(rel_m.group(1))
        if n is not None:
            when = now + timedelta(seconds=n * _REL_SECS[rel_m.group(2)])

    if when is None and hour is not None and 0 <= hour <= 23:
        when = (now + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute or 0, second=0, microsecond=0)
        # 没提今天/明天，而时间已过 → 默认顺延到明天
        if day_offset == 0 and when <= now:
            when += timedelta(days=1)

    content = text
    content = re.sub(r'(今天|明天|后天|大后天)', '', content)
    content = _TIME_RE.sub('', content)
    content = re.sub(r'[过再]?\s*[零一二两三四五六七八九十\d]+\s*(?:秒钟|分钟|小时|钟头|秒|分)\s*(?:后|以后)', '', content)
    content = re.sub(r'(提醒我|提醒|叫我|给我提个醒|记一下|记着|别忘了)', '', content)
    content = re.sub(r'[，。,.！!？?、\s~～]', '', content)
    return when, content


def fmt_when(dt):
    now = datetime.now()
    if dt.date() == now.date():
        day = '今天'
    elif dt.date() == (now + timedelta(days=1)).date():
        day = '明天'
    elif dt.date() == (now + timedelta(days=2)).date():
        day = '后天'
    else:
        day = dt.strftime('%m月%d日')
    t = str(dt.hour) + '点' + (str(dt.minute) + '分' if dt.minute else '')
    return day + t


class ReminderStore:
    """线程安全的本地提醒仓库；原子写盘，服务重启后恢复未完成提醒。"""

    def __init__(self, path=None):
        self._path = Path(path) if path else Path(__file__).resolve().parent.parent / 'reminders.json'
        self._items = []
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding='utf-8'))
            if not isinstance(data, list):
                raise ValueError('reminders.json 必须是列表')
            for obj in data:
                if not isinstance(obj, dict):
                    continue
                when = datetime.fromisoformat(obj['when'])
                content = str(obj['content']).strip()
                if content and not obj.get('notified', False):
                    self._items.append({'id': str(obj.get('id') or uuid.uuid4().hex[:8]),
                                        'when': when, 'content': content, 'notified': False})
            self._items.sort(key=lambda x: x['when'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print('[REMINDER] 无法读取原有提醒，未覆盖文件：', exc)
            raise RuntimeError('提醒存储文件损坏，请先备份或修复：' + str(self._path)) from exc

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [{'id': i['id'], 'when': i['when'].isoformat(timespec='seconds'),
                 'content': i['content'], 'notified': i['notified']} for i in self._items]
        tmp = self._path.with_name(self._path.name + '.tmp')
        try:
            with tmp.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def add(self, when, content):
        item = {'id': uuid.uuid4().hex[:8], 'when': when, 'content': content, 'notified': False}
        with self._lock:
            self._items.append(item)
            self._items.sort(key=lambda x: x['when'])
            self._save()
        return item

    def list(self):
        with self._lock:
            return [{'when': i['when'], 'content': i['content']} for i in self._items]

    def cancel(self, key):
        """按内容关键词取消；key 为空则取消全部。返回取消条数。"""
        with self._lock:
            before = len(self._items)
            if not key:
                self._items = []
            else:
                self._items = [i for i in self._items if key not in i['content']]
            n = before - len(self._items)
            if n:
                self._save()
            return n

    def due_now(self, now=None):
        now = now or datetime.now()
        with self._lock:
            due = [{'content': i['content'], 'when': fmt_when(i['when'])}
                   for i in self._items if i['when'] <= now and not i['notified']]
            if due:
                self._items = [i for i in self._items if i['when'] > now or i['notified']]
                self._save()
            return due


class ReminderTask:
    """一次“设提醒”对话的状态机（查看/取消作为即时命令处理）。"""

    def __init__(self, store):
        self.store = store
        self.stage = 'ask'
        self.when = None
        self.content = ''

    def handle(self, text):
        text = (text or '').strip()

        if self._is_list_cmd(text):
            return self._list_result()
        if self._is_cancel_cmd(text):
            return self._cancel_result(text)

        if is_negate(text):
            self.stage = CANCELLED
            return self._result('好的，那就不设这个提醒了。', active=False)

        if self.stage == 'confirm':
            if is_affirm(text):
                self.store.add(self.when, self.content)
                self.stage = DONE
                res = self._result(
                    '好嘞，' + fmt_when(self.when) + '我会提醒您「' + self.content + '」。',
                    active=False, done=True)
                res['reminder'] = fmt_when(self.when) + ' ' + self.content
                return res
            return self._confirm()

        when, content = parse_reminder(text)
        if when is not None:
            self.when = when
        if content:
            self.content = content

        if self.content and self.when is not None:
            self.stage = 'confirm'
            return self._confirm()
        if self.content and self.when is None:
            self.stage = 'ask_time'
            return self._result('好的，提醒您「' + self.content + '」，几点提醒您呀？比如早上八点、下午三点。')
        if self.when is not None and not self.content:
            self.stage = 'ask_content'
            return self._result('好的，' + fmt_when(self.when) + '，提醒您做什么呀？')
        self.stage = 'ask'
        return self._result('您想提醒什么呀？比如「明天早上八点提醒我出门」。')

    def _confirm(self):
        return self._result('我记住了：' + fmt_when(self.when) + '提醒您「' + self.content + '」，说「好」我就记下。', confirm=True)

    def _is_list_cmd(self, text):
        return (bool(re.search(r'(有哪些|查看|看看|几个|列表|都啥|都有啥|什么).{0,3}提醒', text))
                or text.strip() in ('提醒', '查看提醒', '我的提醒'))

    def _is_cancel_cmd(self, text):
        return '提醒' in text and bool(re.search(r'(取消|删除|删掉|不要|关掉|撤销)', text))

    def _list_result(self):
        items = self.store.list()
        if not items:
            return self._result('您还没有设置提醒。您可以说「明天早上八点提醒我出门」。', active=False)
        parts = ['您当前有 ' + str(len(items)) + ' 条提醒。']
        for i, r in enumerate(items, 1):
            parts.append('第' + str(i) + '条，' + fmt_when(r['when']) + '，' + r['content'] + '。')
        parts.append('到点我会提醒您。')
        return self._result(''.join(parts), active=False)

    def _cancel_result(self, text):
        key = re.sub(r'(取消|删除|删掉|不要|关掉|撤销|提醒|的|这个|那个)', '', text)
        key = re.sub(r'[，。,.！!？?、\s~～]', '', key)
        n = self.store.cancel(key)
        if n == 0:
            return self._result('没有找到要取消的提醒。您可以说「查看提醒」看看有哪些。', active=False)
        return self._result('好的，已取消 ' + str(n) + ' 条提醒。', active=False)

    def _result(self, reply, active=True, done=False, confirm=False):
        return {'reply': reply, 'stage': self.stage, 'active': active, 'done': done, 'confirm': confirm}

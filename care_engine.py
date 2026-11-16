# -*- coding: utf-8 -*-
"""P3.0 主动照护引擎。

把「察觉 → 关心 → 行动 → 回应 → 家人可见」做成一条可轮询的链路：
  - 老人端每 30 秒问一次“此刻该做什么”，服务端按时间和规则给出**一件事**。
  - 每件事用 event_key 幂等，轮询不会重复创建，也不会一次冒出一堆。
  - 老人回应（知道了 / 过半小时 / 不用了）后，子女端能看到状态。
  - 只做确定性文案，不调用大模型，不做健康诊断。
"""
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import auth_v4
import upgrade_services  # noqa: F401  确保 family_links 表已创建
from features.weather_life import current_weather, _weather_tip

CN_TZ = timezone(timedelta(hours=8), 'Asia/Shanghai')

KINDS = ('greet_morning', 'meal_lunch', 'meal_dinner', 'bedtime', 'weather', 'welcome_back')

_ADDR = {'grandma': '奶奶', 'grandpa': '爷爷', 'both': '爷爷奶奶'}

# 窗口起、窗口止、优先级、过期时间（小时,分钟）
_WINDOWS = {
    'greet_morning': ((7, 0), (10, 0), 60, (10, 30)),
    'weather':       ((7, 0), (10, 0), 70, (12, 0)),
    'meal_lunch':    ((11, 30), (13, 0), 90, (13, 30)),
    'meal_dinner':   ((17, 30), (19, 0), 90, (19, 30)),
    'bedtime':       ((21, 0), (22, 0), 90, (23, 0)),
}
_WELCOME_WINDOW = ((7, 0), (21, 0))
_WELCOME_MIN_GAP = 3 * 3600
_WELCOME_MAX_GAP = 12 * 3600
_NO_RESPONSE_SECONDS = 30 * 60

_PHRASES = {
    'greet_morning': {
        'shaanxi': ('早上好呀，{addr}！', '夜里睡得咋样？起来先喝口热水，慢慢拾掇，不着急。'),
        'mandarin': ('早上好，{addr}！', '昨晚睡得好吗？起来先喝口热水，慢慢来，不着急。'),
    },
    'meal_lunch': {
        'shaanxi': ('{addr}，晌午啦', '先歇一歇，吃口热乎饭。吃完坐一会儿再忙。'),
        'mandarin': ('{addr}，该吃午饭啦', '先歇一歇，吃口热乎饭。吃完坐一会儿，别急着忙。'),
    },
    'meal_dinner': {
        'shaanxi': ('{addr}，天擦黑啦', '晚饭吃点清淡的，别吃太饱，吃完咱慢慢走两步。'),
        'mandarin': ('{addr}，该吃晚饭啦', '晚饭吃点清淡的，别吃太饱，吃完慢慢走两步。'),
    },
    'bedtime': {
        'shaanxi': ('{addr}，不早啦', '泡泡脚，把手机放远些，早点歇着。我在这儿守着。'),
        'mandarin': ('{addr}，该歇着啦', '泡泡脚，把手机放远些，早点休息。我在这儿陪着您。'),
    },
    'welcome_back': {
        'shaanxi': ('{addr}，您回来啦', '刚才没听见您说话，我有点惦记。您还好吧？'),
        'mandarin': ('{addr}，您回来啦', '刚才没听见您说话，我有点儿惦记。您还好吗？'),
    },
}

_WEATHER = {'ts': 0, 'ok': False, 'data': None}
_WEATHER_LOCK = threading.Lock()


# ---------------------------------------------------------------- 基础工具

def _now():
    return datetime.now(CN_TZ)


def _ts(dt=None):
    return int((dt or _now()).timestamp())


def _minutes_of(hhmm):
    try:
        h, m = str(hhmm).split(':')
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def _in_minutes(minute, start, end):
    return start[0] * 60 + start[1] <= minute < end[0] * 60 + end[1]


def _in_quiet(now, settings):
    m = now.hour * 60 + now.minute
    s = _minutes_of(settings.get('quiet_start') or '22:00')
    e = _minutes_of(settings.get('quiet_end') or '07:00')
    if s == e:
        return False
    return (m >= s or m < e) if s > e else (s <= m < e)


def _day_str(dt):
    return dt.strftime('%Y-%m-%d')


def _day_start_ts(dt):
    return int(datetime(dt.year, dt.month, dt.day, tzinfo=CN_TZ).timestamp())


def _addr_for(user):
    return _ADDR.get(user.get('addressee'), '奶奶')


def _need_elder(user):
    if not user or user.get('role') != 'elder':
        raise PermissionError('仅老人账号可以使用主动关怀')


def _need_family(user):
    if not user or user.get('role') != 'family':
        raise PermissionError('仅家人账号可以查看照护动态')


def _public_settings(row):
    return {
        'enabled': bool(row.get('enabled')),
        'quiet_start': row.get('quiet_start') or '22:00',
        'quiet_end': row.get('quiet_end') or '07:00',
        'max_per_day': int(row.get('max_per_day') or 8),
        'updated_at': int(row.get('updated_at') or 0),
    }


def _settings_row(con, elder_id):
    row = con.execute('SELECT * FROM care_settings WHERE elder_id=?', (elder_id,)).fetchone()
    if row:
        return dict(row)
    now = int(time.time())
    con.execute(
        'INSERT OR IGNORE INTO care_settings(elder_id,enabled,quiet_start,quiet_end,max_per_day,updated_at)'
        ' VALUES(?,?,?,?,?,?)',
        (elder_id, 1, '22:00', '07:00', 8, now))
    row = con.execute('SELECT * FROM care_settings WHERE elder_id=?', (elder_id,)).fetchone()
    return dict(row)


# ---------------------------------------------------------------- 天气

def _weather_snapshot():
    """30 分钟成功缓存 / 5 分钟失败缓存；网络请求不持有数据库锁。"""
    with _WEATHER_LOCK:
        now = time.time()
        ttl = 1800 if _WEATHER['ok'] else 300
        if _WEATHER['ts'] and now - _WEATHER['ts'] < ttl:
            return _WEATHER['data']
        try:
            data = current_weather()
        except Exception:  # noqa: BLE001
            data = None
        _WEATHER['ts'] = now
        _WEATHER['ok'] = bool(data)
        _WEATHER['data'] = data
        return data


def _weather_needed(weather):
    if not weather:
        return False
    desc = str(weather.get('desc') or '')
    if re.search(r'(雨|雪|雷|雾|霾|沙)', desc):
        return True
    try:
        tmin = float(weather.get('tmin'))
        tmax = float(weather.get('tmax'))
    except (TypeError, ValueError):
        return False
    return tmin <= 5 or tmax >= 33


def _weather_text(addr, lang, weather):
    if not weather:
        if lang == 'mandarin':
            return ('{addr}，今天天气'.format(addr=addr),
                    '天气一时没查到，出门前看看窗外最准。')
        return ('{addr}，今儿天气'.format(addr=addr),
                '天气一时没查到，出门前看看窗外最准。')
    desc = weather.get('desc') or '天气还行'
    tmin = weather.get('tmin')
    tmax = weather.get('tmax')
    tip = ''
    try:
        tip = _weather_tip(desc, float(tmin), float(tmax))
    except (TypeError, ValueError):
        tip = '出门前看看窗外，注意冷暖。'
    if lang == 'mandarin':
        title = '{addr}，今天{desc}'.format(addr=addr, desc=desc)
        body = '最高{tmax}度、最低{tmin}度。{tip}'.format(tmin=tmin, tmax=tmax, tip=tip)
    else:
        title = '{addr}，今儿{desc}'.format(addr=addr, desc=desc)
        body = '最高{tmax}度、最低{tmin}度。{tip}'.format(tmin=tmin, tmax=tmax, tip=tip)
    return title, body


def _text_for(kind, addr, lang, weather=None):
    """纯文案函数：绝不联网。天气数据由调用方在数据库锁外取好后传入。"""
    lang = 'mandarin' if lang == 'mandarin' else 'shaanxi'
    if kind == 'weather':
        return _weather_text(addr, lang, weather)
    title, body = _PHRASES[kind][lang]
    return title.format(addr=addr), body.format(addr=addr)


# ---------------------------------------------------------------- 建事件

def _insert(con, elder_id, kind, event_key, title, body, priority, created_at, expires_at,
            demo=0, ref_id=None):
    cur = con.execute(
        'INSERT INTO care_events(elder_id,kind,event_key,title,body,priority,created_at,'
        'expires_at,demo,ref_id) VALUES(?,?,?,?,?,?,?,?,?,?)'
        ' ON CONFLICT(elder_id,event_key) DO NOTHING',
        (elder_id, kind, event_key, title, body, priority, created_at, expires_at, demo, ref_id))
    return cur.rowcount > 0


def _build_candidates(con, user, settings, now, day, minute, weather, last_seen, lang,
                      has_weather=False):
    elder_id = user['id']
    addr = _addr_for(user)
    created = 0
    cap = max(1, int(settings.get('max_per_day') or 8))
    start_ts = _day_start_ts(now)
    count = con.execute(
        'SELECT COUNT(*) AS n FROM care_events WHERE elder_id=? AND demo=0 AND created_at>=?',
        (elder_id, start_ts)).fetchone()['n']

    def add(kind, priority, expire_hm):
        nonlocal created, count
        if count >= cap:
            return False
        title, body = _text_for(kind, addr, lang, weather)
        expires = int(datetime(now.year, now.month, now.day, expire_hm[0], expire_hm[1],
                               tzinfo=CN_TZ).timestamp())
        if _insert(con, elder_id, kind, kind + ':' + day, title, body, priority,
                   _ts(now), expires):
            created += 1
            count += 1
            return True
        return False

    for kind in ('meal_lunch', 'meal_dinner', 'bedtime'):
        win = _WINDOWS[kind]
        if _in_minutes(minute, win[0], win[1]):
            add(kind, win[2], win[3])

    # 久未互动后又回来：只当天、间隔 3–12 小时，且当天没有早安事件。
    if last_seen and _in_minutes(minute, *_WELCOME_WINDOW):
        gap = _ts(now) - int(last_seen)
        same_day = datetime.fromtimestamp(int(last_seen), CN_TZ).strftime('%Y-%m-%d') == day
        has_greet = con.execute(
            'SELECT 1 FROM care_events WHERE elder_id=? AND kind=? AND event_key=?',
            (elder_id, 'greet_morning', 'greet_morning:' + day)).fetchone()
        if same_day and _WELCOME_MIN_GAP <= gap <= _WELCOME_MAX_GAP and not has_greet:
            add('welcome_back', 85, (23, 59))

    if not has_weather and _in_minutes(minute, *_WINDOWS['weather'][:2]) and _weather_needed(weather):
        add('weather', _WINDOWS['weather'][2], _WINDOWS['weather'][3])

    if _in_minutes(minute, *_WINDOWS['greet_morning'][:2]):
        add('greet_morning', _WINDOWS['greet_morning'][2], _WINDOWS['greet_morning'][3])

    return created > 0


# ---------------------------------------------------------------- 序列化

def _event_dict(row, now_ts):
    snooze = row['snooze_until']
    base = max(int(row['created_at']), int(snooze or 0))
    return {
        'id': row['id'],
        'kind': row['kind'],
        'title': row['title'],
        'body': row['body'],
        'priority': row['priority'],
        'created_at': row['created_at'],
        'expires_at': row['expires_at'],
        'snooze_until': snooze,
        'demo': bool(row['demo']),
        'age_seconds': max(0, now_ts - int(row['created_at'])),
        'is_fresh': (now_ts - base) <= 120,
        'delivery_key': '%s:%s' % (row['id'], snooze or 0),
        'actions': ['done', 'snooze', 'dismiss'],
    }


def _feed_status(row, now_ts):
    if row['ack_kind'] in ('done', 'dismiss'):
        return 'responded'
    if row['ack_kind'] == 'snooze':
        until = int(row['snooze_until'] or row['created_at'])
        if until > now_ts:
            return 'snoozed'
        return 'no_response' if now_ts - until >= _NO_RESPONSE_SECONDS else 'waiting'
    if row['ack_at'] is None:
        return 'no_response' if now_ts - int(row['created_at']) >= _NO_RESPONSE_SECONDS else 'waiting'
    return 'responded'


def _stats(con, elder_id, now_ts, cap):
    start_ts = _day_start_ts(_now())
    rows = con.execute(
        'SELECT ack_at,ack_kind FROM care_events WHERE elder_id=? AND demo=0 AND created_at>=?',
        (elder_id, start_ts)).fetchall()
    total = len(rows)
    responded = sum(1 for r in rows if r['ack_kind'] in ('done', 'dismiss'))
    return {'today_total': total, 'responded': responded,
            'pending': max(0, total - responded), 'cap': cap}


def _pending_row(con, elder_id, now_ts):
    return con.execute(
        'SELECT * FROM care_events WHERE elder_id=?'
        ' AND (expires_at IS NULL OR expires_at>?)'
        ' AND ((ack_at IS NULL AND (snooze_until IS NULL OR snooze_until<=?))'
        '      OR (ack_kind=? AND snooze_until IS NOT NULL AND snooze_until<=?))'
        ' ORDER BY priority DESC, created_at ASC LIMIT 1',
        (elder_id, now_ts, now_ts, 'snooze', now_ts)).fetchone()


# ---------------------------------------------------------------- 对外接口

def settings_get(user):
    _need_elder(user)
    with auth_v4.db() as con:
        row = _settings_row(con, user['id'])
    return {'ok': True, 'settings': _public_settings(row)}


def settings_set(user, data):
    _need_elder(user)
    if not isinstance(data, dict):
        raise ValueError('参数格式不正确')
    with auth_v4._LOCK, auth_v4.db() as con:
        row = _settings_row(con, user['id'])
        enabled = row['enabled']
        quiet_start = row['quiet_start']
        quiet_end = row['quiet_end']
        max_per_day = int(row['max_per_day'])
        if 'enabled' in data:
            enabled = 1 if data.get('enabled') in (True, 1, '1', 'true', 'on') else 0
        for key in ('quiet_start', 'quiet_end'):
            if key in data:
                value = str(data.get(key) or '')
                if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', value):
                    raise ValueError('时间请使用 HH:MM 格式')
                if key == 'quiet_start':
                    quiet_start = value
                else:
                    quiet_end = value
        if 'max_per_day' in data:
            try:
                max_per_day = int(data.get('max_per_day'))
            except (TypeError, ValueError):
                raise ValueError('每日条数需为 1–12')
            if not 1 <= max_per_day <= 12:
                raise ValueError('每日条数需为 1–12')
        con.execute(
            'INSERT INTO care_settings(elder_id,enabled,quiet_start,quiet_end,max_per_day,updated_at)'
            ' VALUES(?,?,?,?,?,?) ON CONFLICT(elder_id) DO UPDATE SET'
            ' enabled=excluded.enabled,quiet_start=excluded.quiet_start,'
            'quiet_end=excluded.quiet_end,max_per_day=excluded.max_per_day,'
            'updated_at=excluded.updated_at',
            (user['id'], enabled, quiet_start, quiet_end, max_per_day, int(time.time())))
        row = _settings_row(con, user['id'])
    return {'ok': True, 'settings': _public_settings(row)}


def today(user, lang='shaanxi'):
    _need_elder(user)
    lang = 'mandarin' if str(lang).lower() == 'mandarin' else 'shaanxi'
    now = _now()
    now_ts = _ts(now)
    day = _day_str(now)
    minute = now.hour * 60 + now.minute

    # 天气在数据库锁外取；只有窗口内且当天还没有天气事件时才联网。
    weather = None
    with auth_v4.db() as con:
        has_weather = con.execute(
            'SELECT 1 FROM care_events WHERE elder_id=? AND event_key=?',
            (user['id'], 'weather:' + day)).fetchone()
    if not has_weather and _in_minutes(minute, *_WINDOWS['weather'][:2]):
        weather = _weather_snapshot()

    with auth_v4._LOCK, auth_v4.db() as con:
        settings = _settings_row(con, user['id'])
        act = con.execute('SELECT last_seen FROM care_activity WHERE elder_id=?',
                          (user['id'],)).fetchone()
        last_seen = act['last_seen'] if act else 0

        if settings['enabled'] and not _in_quiet(now, settings):
            _build_candidates(con, user, settings, now, day, minute, weather, last_seen, lang,
                              bool(has_weather))

        if now_ts - int(last_seen or 0) >= 60:
            con.execute(
                'INSERT INTO care_activity(elder_id,last_seen) VALUES(?,?)'
                ' ON CONFLICT(elder_id) DO UPDATE SET last_seen=excluded.last_seen',
                (user['id'], now_ts))

        row = _pending_row(con, user['id'], now_ts) if settings['enabled'] else None
        snoozed_until = None
        if row is None and settings['enabled']:
            r2 = con.execute(
                'SELECT MIN(snooze_until) AS t FROM care_events WHERE elder_id=?'
                ' AND ack_kind=? AND snooze_until>? AND (expires_at IS NULL OR expires_at>?)',
                (user['id'], 'snooze', now_ts, now_ts)).fetchone()
            snoozed_until = r2['t'] if r2 and r2['t'] else None
        stats = _stats(con, user['id'], now_ts, int(settings['max_per_day']))

    return {
        'ok': True,
        'server_time': now.isoformat(timespec='seconds'),
        'date': day,
        'settings': _public_settings(settings),
        'stats': stats,
        'event': _event_dict(row, now_ts) if row else None,
        'snoozed_until': snoozed_until,
    }


def ack(user, event_id, action, minutes=30):
    _need_elder(user)
    action = str(action or '')
    if action not in ('done', 'snooze', 'dismiss'):
        raise ValueError('操作无效')
    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        raise ValueError('关怀事件无效')
    if action == 'snooze':
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = 30
        minutes = max(1, min(120, minutes))
    now_ts = int(time.time())

    with auth_v4._LOCK, auth_v4.db() as con:
        row = con.execute('SELECT * FROM care_events WHERE id=? AND elder_id=?',
                          (event_id, user['id'])).fetchone()
        if not row:
            raise ValueError('没有找到这条关怀')
        already = row['ack_at'] is not None and row['ack_kind'] != 'snooze'
        if not already:
            if action == 'snooze':
                con.execute(
                    "UPDATE care_events SET ack_at=?,ack_kind='snooze',snooze_until=?"
                    ' WHERE id=? AND elder_id=?',
                    (now_ts, now_ts + minutes * 60, event_id, user['id']))
            else:
                con.execute(
                    'UPDATE care_events SET ack_at=?,ack_kind=?,snooze_until=NULL'
                    ' WHERE id=? AND elder_id=?',
                    (now_ts, action, event_id, user['id']))
            row = con.execute('SELECT * FROM care_events WHERE id=?', (event_id,)).fetchone()
        settings = _settings_row(con, user['id'])
        stats = _stats(con, user['id'], now_ts, int(settings['max_per_day']))
        nxt = _pending_row(con, user['id'], now_ts)

    return {
        'ok': True,
        'already': already,
        'event': {
            'id': row['id'],
            'ack_kind': row['ack_kind'],
            'ack_at': row['ack_at'],
            'snooze_until': row['snooze_until'],
        },
        'next_event': _event_dict(nxt, now_ts) if nxt else None,
        'stats': stats,
    }


def feed(user):
    _need_family(user)
    now = _now()
    now_ts = _ts(now)
    start_ts = _day_start_ts(now)
    total = {'responded': 0, 'snoozed': 0, 'waiting': 0, 'no_response': 0, 'total': 0}

    with auth_v4._LOCK, auth_v4.db() as con:
        elders = con.execute(
            '''SELECT l.elder_id AS id, u.username, u.addressee,
                      COALESCE(n.nickname,'') AS nickname
               FROM family_links l
               JOIN users u ON u.id=l.elder_id
               LEFT JOIN user_nicknames n ON n.user_id=l.elder_id
               WHERE l.family_id=? ORDER BY l.elder_id''',
            (user['id'],)).fetchall()

        result = []
        for e in elders:
            settings = _settings_row(con, e['id'])
            rows = con.execute(
                'SELECT * FROM care_events WHERE elder_id=? AND created_at>=?'
                ' ORDER BY created_at DESC LIMIT 50',
                (e['id'], start_ts)).fetchall()
            events = []
            summary = {'responded': 0, 'snoozed': 0, 'waiting': 0, 'no_response': 0, 'total': 0}
            for r in rows:
                status = _feed_status(r, now_ts)
                summary[status] += 1
                summary['total'] += 1
                total[status] += 1
                total['total'] += 1
                events.append({
                    'id': r['id'],
                    'kind': r['kind'],
                    'title': r['title'],
                    'body': r['body'],
                    'created_at': r['created_at'],
                    'time': datetime.fromtimestamp(int(r['created_at']), CN_TZ).strftime('%H:%M'),
                    'ack_kind': r['ack_kind'],
                    'ack_at': r['ack_at'],
                    'snooze_until': r['snooze_until'],
                    'status': status,
                    'demo': bool(r['demo']),
                })
            result.append({
                'id': e['id'],
                'name': e['nickname'] or _ADDR.get(e['addressee'], '') or e['username'],
                'username': e['username'],
                'avatar': '',
                'addressee': e['addressee'],
                'enabled': bool(settings['enabled']),
                'summary': summary,
                'events': events,
            })

    return {
        'ok': True,
        'date': _day_str(now),
        'generated_at': now_ts,
        'summary': total,
        'elders': result,
        'unbound': not result,
    }


def preview(user, kind, lang='shaanxi', age_minutes=0):
    if os.environ.get('XLJ_CARE_DEMO', '1').lower() in ('0', 'false', 'off'):
        raise PermissionError('演示开关已关闭')
    _need_elder(user)
    kind = str(kind or '')
    if kind not in KINDS:
        raise ValueError('未知的关怀类型')
    try:
        age_minutes = max(0, min(1440, int(age_minutes)))
    except (TypeError, ValueError):
        age_minutes = 0
    now_ts = int(time.time())
    created = now_ts - age_minutes * 60
    addr = _addr_for(user)
    title, body = _text_for(kind, addr, lang, _weather_snapshot() if kind == 'weather' else None)
    with auth_v4._LOCK, auth_v4.db() as con:
        con.execute('DELETE FROM care_events WHERE elder_id=? AND demo=1 AND ack_at IS NULL',
                    (user['id'],))
        con.execute(
            'INSERT INTO care_events(elder_id,kind,event_key,title,body,priority,created_at,'
            'expires_at,demo,ref_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (user['id'], kind, 'demo:%s:%s' % (kind, time.time_ns()), title, body, 999,
             created, now_ts + 3600, 1, None))
        row = con.execute('SELECT * FROM care_events WHERE elder_id=? AND demo=1'
                          ' ORDER BY id DESC LIMIT 1', (user['id'],)).fetchone()
    return {'ok': True, 'event': _event_dict(row, now_ts)}


# ---------------------------------------------------------------- 初始化

def init():
    with auth_v4._LOCK, auth_v4.db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS care_events (
          id INTEGER PRIMARY KEY,
          elder_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          event_key TEXT NOT NULL,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL,
          expires_at INTEGER,
          ack_at INTEGER,
          ack_kind TEXT CHECK(ack_kind IN ('done','snooze','dismiss')),
          snooze_until INTEGER,
          demo INTEGER NOT NULL DEFAULT 0,
          ref_id INTEGER,
          UNIQUE(elder_id, event_key)
        );
        CREATE INDEX IF NOT EXISTS idx_care_events_elder
          ON care_events(elder_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_care_events_pending
          ON care_events(elder_id, ack_at, snooze_until);

        CREATE TABLE IF NOT EXISTS care_settings (
          elder_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          enabled INTEGER NOT NULL DEFAULT 1,
          quiet_start TEXT NOT NULL DEFAULT '22:00',
          quiet_end TEXT NOT NULL DEFAULT '07:00',
          max_per_day INTEGER NOT NULL DEFAULT 8,
          updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS care_activity (
          elder_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          last_seen INTEGER NOT NULL
        );
        ''')


init()

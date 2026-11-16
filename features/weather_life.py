# -*- coding: utf-8 -*-
"""天气及生活查询：天气（open-meteo 免 key）+ 日期/星期 + 时间 + 二十四节气。

天气是真实联网查询（open-meteo 免费接口，无需密钥）；日期/时间/节气按本地日历算，
节气公历日期为近似值（误差一般 1 天内），演示够用，不谎报精确农历。
"""
import json
import re
import urllib.error
import urllib.request
from datetime import datetime

LAT = 34.33   # 老人所在村纬度（陕西咸阳）
LON = 108.71  # 老人所在村经度

WEATHER_DESC = {
    0: '大晴天', 1: '晴天', 2: '多云', 3: '阴天', 45: '有雾', 48: '有雾',
    51: '小雨', 53: '小雨', 55: '小雨', 61: '下雨', 63: '中雨', 65: '大雨',
    66: '冻雨', 67: '冻雨', 71: '小雪', 73: '中雪', 75: '大雪', 77: '雪粒',
    80: '阵雨', 81: '阵雨', 82: '暴雨', 85: '阵雪', 86: '阵雪',
    95: '雷阵雨', 96: '雷阵雨', 99: '雷阵雨',
}

# 二十四节气（近似公历日期：月、日、名称）
SOLAR_TERMS = [
    (1, 5, '小寒'), (1, 20, '大寒'), (2, 4, '立春'), (2, 19, '雨水'),
    (3, 5, '惊蛰'), (3, 20, '春分'), (4, 5, '清明'), (4, 20, '谷雨'),
    (5, 5, '立夏'), (5, 21, '小满'), (6, 6, '芒种'), (6, 21, '夏至'),
    (7, 7, '小暑'), (7, 23, '大暑'), (8, 7, '立秋'), (8, 23, '处暑'),
    (9, 7, '白露'), (9, 23, '秋分'), (10, 8, '寒露'), (10, 23, '霜降'),
    (11, 7, '立冬'), (11, 22, '小雪'), (12, 7, '大雪'), (12, 22, '冬至'),
]

WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']


def _season(now):
    m = now.month
    if m in (3, 4, 5):
        return '春天'
    if m in (6, 7, 8):
        return '夏天'
    if m in (9, 10, 11):
        return '秋天'
    return '冬天'


def _solar_terms_around(now):
    cur, nxt = None, None
    for m, d, name in SOLAR_TERMS:
        if datetime(now.year, m, d) <= now:
            cur = (m, d, name)
        else:
            nxt = (m, d, name)
            break
    if cur is None:
        cur = (12, 22, '冬至')
    if nxt is None:
        nxt = (1, 5, '小寒')
    return cur, nxt


def _time_reply(now):
    h = now.hour
    if h < 6:
        period = '凌晨'
    elif h < 9:
        period = '早上'
    elif h < 12:
        period = '上午'
    elif h < 14:
        period = '中午'
    elif h < 18:
        period = '下午'
    else:
        period = '晚上'
    hh = h % 12 or 12
    return '现在是%s%d点%d分。' % (period, hh, now.minute)


def _date_reply(now):
    return '今天是%d月%d日，%s。' % (now.month, now.day, WEEKDAYS[now.weekday()])


def _solar_reply(now):
    cur, nxt = _solar_terms_around(now)
    return '现在是%s，正赶上「%s」节气，下一个节气是%d月%d日的「%s」。' % (
        _season(now), cur[2], nxt[0], nxt[1], nxt[2])


def _weather_tip(desc, tmin, tmax):
    if re.search(r'(雨|雪|雷|雾)', desc):
        return '出门记得带伞。'
    if tmin < 5:
        return '天冷，多穿件棉袄。'
    if tmin < 12:
        return '有点凉，加件外套。'
    if tmax > 30:
        return '天热，穿凉快些。'
    return '天气不错，放心出门。'


def _weather_reply(text):
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s'
           '&daily=weathercode,temperature_2m_max,temperature_2m_min'
           '&timezone=Asia%%2FShanghai&forecast_days=2') % (LAT, LON)
    import time
    j = None
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.loads(r.read().decode('utf-8'))
            break
        except Exception:
            if attempt == 2:
                return '天气我一时没查到，您明早起来看看窗外最准。'
            time.sleep(1.5)  # 偶发限流/网络抖动，退避重试一次
    try:
        d = j['daily']
        idx = 0 if re.search(r'(今天|今儿|现在)', text) else 1  # 默认查明天
        wc = d['weathercode'][idx]
        tmax = d['temperature_2m_max'][idx]
        tmin = d['temperature_2m_min'][idx]
        desc = WEATHER_DESC.get(wc, '天气还行')
        parts = (d['time'][idx] or '').split('-')
        md = ('%d月%d日' % (int(parts[1]), int(parts[2]))) if len(parts) >= 3 else ''
        label = '今天' if idx == 0 else '明天'
        return '%s（%s）咱这儿是%s，最高%d度、最低%d度。%s' % (
            label, md, desc, round(tmax), round(tmin), _weather_tip(desc, tmin, tmax))
    except Exception:
        return '天气我一时没查到，您明早起来看看窗外最准。'


def current_weather():
    """真实天气：Open-Meteo 当前温度、风、湿度及逐小时预报。失败返回 None。"""
    url = ('https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s'
           '&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m'
           '&hourly=temperature_2m,weather_code'
           '&daily=weather_code,temperature_2m_max,temperature_2m_min'
           '&timezone=Asia%%2FShanghai&forecast_days=1') % (LAT,LON)
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'XiaoLaJiao/2.6'})
        with urllib.request.urlopen(req,timeout=12) as r:j=json.load(r)
        d=j['daily'];c=j['current'];h=j.get('hourly',{})
        now=c.get('time','');times=h.get('time',[]);hourly=[]
        for i,t in enumerate(times):
            if t>=now[:13]:
                hourly.append({'time':t[11:16], 'temp':round(h['temperature_2m'][i]),'desc':WEATHER_DESC.get(h['weather_code'][i],'')})
            if len(hourly)>=8:break
        return {'city':'陕西咸阳附近','desc':WEATHER_DESC.get(c['weather_code'],'天气状况未知'),
                'temp':round(c['temperature_2m']),'humidity':c.get('relative_humidity_2m'),
                'wind':c.get('wind_speed_10m'),'tmin':round(d['temperature_2m_min'][0]),
                'tmax':round(d['temperature_2m_max'][0]),'hourly':hourly,
                'alert':'当前接口不提供官方预警信息','updated':now}
    except (KeyError,ValueError,TypeError,urllib.error.URLError,TimeoutError):
        return None


class LifeQueryTask:
    """一次“天气/日期/时间/节气”查询（无状态，一问一答）。"""

    def handle(self, text):
        text = (text or '').strip()
        now = datetime.now()

        # 时间（排除“今天几点下雨”这类其实是问天气的）
        if re.search(r'(几点|几点了|几点钟|现在时间|什么时候|啥时候|几时|报时)', text) \
                and not re.search(r'(天气|下雨|下雪|几号|星期|节气)', text):
            return self._result(_time_reply(now))

        # 日期 / 星期
        if re.search(r'(几号|几月几|星期|周几|礼拜|什么日子|哪天|日期|日历)', text):
            return self._result(_date_reply(now))

        # 节气 / 季节
        if re.search(r'(节气|季节|春天|夏天|秋天|冬天)', text):
            return self._result(_solar_reply(now))

        # 天气
        if re.search(r'(天气|下雨|下雪|降温|升温|冷不冷|热不热|几度|温度|气温|带伞|穿什么|晴天|阴天|多云|刮风|风大)', text):
            return self._result(_weather_reply(text))

        return self._result('您想问天气、今天几号、现在几点，还是到啥节气了？我都能帮您查。')

    def _result(self, reply):
        return {'reply': reply, 'active': False}

# -*- coding: utf-8 -*-
"""秦腔娱乐中心：本地曲库 + 可配置的合法在线音频链接 + 点播/换一段/知识问答。

本地曲目仍来自 audio/ 目录；在线曲目从项目根目录的 qinqiang_online.json 读取。
在线链接必须是你有权使用、且浏览器可以直接播放的音频 URL；本模块不抓取或绕过平台版权限制。
"""
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONLINE_FILE = os.path.join(BASE_DIR, 'qinqiang_online.json')

# 本地曲库：file 对应 audio/ 目录下的 mp3 文件名（不带扩展名）
LOCAL_PLAYLIST = [
    {'id': 'sandixue', 'name': '秦腔《三滴血》', 'file': 'qinqiang', 'type': '唱段',
     'desc': '经典名剧，周天佑认亲的故事', 'source': 'local'},
    {'id': 'huoyanju', 'name': '秦腔《火焰驹》', 'file': 'qinqiang_huoyanju', 'type': '导赏',
     'desc': '易俗社看家戏，黄桂英与李彦贵的爱情', 'source': 'local'},
    {'id': 'zhouren', 'name': '秦腔《周仁回府》', 'file': 'qinqiang_zhouren', 'type': '导赏',
     'desc': '周仁义救嫂嫂的须生名剧', 'source': 'local'},
    {'id': 'wudianpo', 'name': '秦腔《五典坡》', 'file': 'qinqiang_wudianpo', 'type': '导赏',
     'desc': '薛平贵与王宝钏，寒窑十八年', 'source': 'local'},
    {'id': 'baishe', 'name': '秦腔《白蛇传》', 'file': 'qinqiang_baishe', 'type': '导赏',
     'desc': '白娘子与许仙，《断桥》最动人', 'source': 'local'},
]

_ALIAS = {
    '三滴血': 'sandixue', '火焰驹': 'huoyanju',
    '周仁回府': 'zhouren', '周仁': 'zhouren',
    '五典坡': 'wudianpo', '王宝钏': 'wudianpo',
    '白蛇传': 'baishe', '白蛇': 'baishe', '白娘子': 'baishe',
}

KNOWLEDGE = [
    {'kw': ['板式', '唱腔', '欢音', '苦音'],
     'text': '秦腔唱腔分欢音、苦音两大类：欢音明快昂扬，苦音深沉悲壮，这是秦腔最独特的味儿。'},
    {'kw': ['名家', '名角', '谁唱'],
     'text': '秦腔名家有马友仙、贠宗翰、李梅等，百年老班社易俗社就是唱秦腔的。'},
    {'kw': ['经典', '名剧', '剧目', '看家戏'],
     'text': '秦腔看家戏有《三滴血》《火焰驹》《周仁回府》《五典坡》，都是老陕爱听的。'},
]
_KNOW_QUERY = re.compile(r'(知识|介绍|讲讲|讲一下|是啥|是什么|起源|历史|由来|板式|唱腔|名家|名角|名剧|剧目|讲究|有啥|说说)')


def _load_online_playlist():
    """读取可选在线曲库。无文件/无效条目时安静回退到本地曲库。"""
    try:
        with open(ONLINE_FILE, 'r', encoding='utf-8') as f:
            items = json.load(f)
        if not isinstance(items, list):
            return []
    except (OSError, json.JSONDecodeError):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get('url', '')).strip()
        track_id = str(item.get('id', '')).strip()
        name = str(item.get('name', '')).strip()
        # 只接受明确的 http/https 链接，避免错误的 src。
        if not (url.startswith('https://') or url.startswith('http://')):
            continue
        if not track_id or not name:
            continue
        result.append({
            'id': track_id,
            'name': name,
            'url': url,
            'type': str(item.get('type') or '在线唱段'),
            'desc': str(item.get('desc') or '在线音频'),
            'source': 'online',
            'aliases': [str(a) for a in item.get('aliases', []) if str(a).strip()],
        })
    return result


def get_playlist():
    """本地曲目优先，在线曲目追加；在线配置在服务启动时由列表接口读取。"""
    return [dict(x) for x in LOCAL_PLAYLIST] + _load_online_playlist()


# 与现有 server.py 的 `from features.qinqiang import ... PLAYLIST` 保持兼容。
# 修改 qinqiang_online.json 后重启 server.py 以刷新这个列表。
PLAYLIST = get_playlist()


class QinqiangTask:
    """一次秦腔会话：点播 / 换一段 / 知识问答。"""
    def __init__(self):
        self.cur_id = None


    def handle(self, text):
        text = (text or '').strip()

        # 1. 秦腔知识问答
        k = self._knowledge(text)
        if k:
            return self._result(k, action='knowledge')

        # 2. 换一段
        if re.search(
            r'(换一段|换一个|换个|换一出|下一段|下一出|再换|换一换)',
            text
        ):
            return self._next()

        # 3. 判断是否明确要求播放
        play_intent = bool(re.search(
            r'(给我|帮我|为我|替我|想听|要听|想看|要看|'
            r'来一段|来段|放一段|放段|播放|放一下|'
            r'播一段|点一段|点一出|唱一段|听一段)',
            text
        ))

        # 排除回忆、叙述和否定表达
        negative = bool(re.search(
            r'(不想|不要|别|先别|不用|停止|暂停|取消)'
            r'.{0,8}(放|播|听|唱)',
            text
        ))

        if negative:
            play_intent = False

        # 4. 只有明确要求播放，才允许点播
        if play_intent:
            tid = self._match_track(text)
            if tid:
                return self._play(tid)

            if re.search(
                r'(秦腔|戏曲|唱戏|听戏|看戏|梆子|戏)',
                text
            ):
                return self._play(get_playlist()[0]['id'])

        # 5. 叙述和回忆不触发播放
        if re.search(
            r'(秦腔|戏曲|唱戏|听戏|看戏|梆子|'
            r'三滴血|火焰驹|周仁|五典坡|白蛇)',
            text
        ):
            return self._result(
                '奶奶，听您这么说，想必以前听戏留下了不少回忆。'
                '您愿意再跟小辣椒讲讲吗？',
                action=None
            )

        return self._result(
            '您想听秦腔哪一出呀？'
            '可以说“给我放三滴血”或者“播放火焰驹”。',
            action=None
        )

    def _match_track(self, text):
        for alias, tid in _ALIAS.items():
            if alias in text:
                return tid
        for track in get_playlist():
            if track['name'] in text or track['id'] in text:
                return track['id']
            if any(alias in text for alias in track.get('aliases', [])):
                return track['id']
        return None

    def _play(self, tid):
        track = next((t for t in get_playlist() if t['id'] == tid), None)
        if not track:
            return self._result('我暂时没找到这段戏，您换个剧名试试，好不好？', action=None)
        self.cur_id = tid
        return self._result('好嘞，这就给您放' + track['name'] + '，您慢慢听。', action='play', track=track)

    def _next(self):
        if self.cur_id is None:
            return self._result('这会儿还没放秦腔呢，您先点一出，比如“放秦腔”或“放火焰驹”。', action=None)
        tracks = get_playlist()
        idx = next((i for i, t in enumerate(tracks) if t['id'] == self.cur_id), 0)
        return self._play(tracks[(idx + 1) % len(tracks)]['id'])

    def _knowledge(self, text):
        if not re.search(r'(秦腔|戏曲|梆子)', text) or not _KNOW_QUERY.search(text):
            return None
        for item in KNOWLEDGE:
            if any(kw in text for kw in item['kw']):
                return item['text']
        return '秦腔是流行于陕西、甘肃等地的传统戏曲剧种，也叫梆子腔。'

    def _result(self, reply, action=None, track=None):
        return {'reply': reply, 'action': action, 'track': track, 'active': False,
                'done': bool(action == 'play'), 'playlist': get_playlist()}

# -*- coding: utf-8 -*-
"""主动陪伴模块：视频陪伴通话里，小辣椒主动暖场、引导话题、自然结束。

分工：
  - 开场问候 / 话题建议 / 冷场接话 / 结束语，由本模块给出（确定性、亲切）。
  - 顺着老人话题追问、延展、切换，交给 DeepSeek（前端注入 COMPANION_SYSTEM_PROMPT）。

状态：opening（开场）→ chatting（聊天中）→ ending（结束）；
另有 silence_nudged 计数，保证沉默安抚只说一次、之后安静陪着不催。
"""
import random

# 陪伴通话专用系统提示词：主动、亲切、简短、一次只问一个问题
COMPANION_SYSTEM_PROMPT = (
    '现在是视频陪伴通话，你正用可爱的形象面对面陪当前使用者聊天解闷。'
    '要主动、亲切，像小孙女一样软软地说话。先理解老人刚说的话，再顺着往下聊、轻轻追问，'
    '一次只问一个问题，不要连珠炮式提问；回复要简短，一般一两句话，别啰嗦、别说套话。'
    '老人明显不想聊时，就主动提议放段秦腔、讲个笑话，或者安静陪着，不要硬找话题、不要催促。'
)

# 开场问候：先问好，再抛一个轻松的开场问题（随机挑，避免每次一样）
_OPENINGS = [
    '{who}，您来啦！今天过得怎么样呀？',
    '{who}，我在这儿呢！今天有没有出去走走、碰到啥开心事呀？',
    '{who}，可算把您等来啦！这会儿心情好不好呀？',
]

# 话题池：日常生活 / 家乡风俗 / 兴趣爱好 / 往事回忆 / 家庭生活
TOPIC_GROUPS = [
    {'name': '日常生活', 'prompts': ['今天都吃了些啥呀？', '这会儿天冷不冷，您添衣裳没？']},
    {'name': '家乡风俗', 'prompts': ['咱这儿过年都有啥讲究呀？', '您小时候村里过庙会热闹不？']},
    {'name': '兴趣爱好', 'prompts': ['您爱听秦腔不？我给您放一段？', '您平时爱种点菜、养点花不？']},
    {'name': '往事回忆', 'prompts': ['您年轻时候有啥难忘的事儿呀？', '给我讲讲您小时候的事儿呗。']},
    {'name': '家庭生活', 'prompts': ['您孙子、孙女多大了呀？', '家里人常回来看您不？']},
]

# 沉默安抚：只说一次，之后安静陪着（由 silence_nudged 计数保证）
_SILENCE_HINTS = [
    '没关系，您慢慢想，不着急。我陪您待一会儿，要不要听段秦腔？',
    '不着急，您歇会儿。我在这儿陪着您，想聊了随时跟我说。',
]

# 自然结束语
_CLOSINGS = [
    '好嘞，那咱今儿就聊到这儿，您多喝水、多休息，想我了随时叫我。',
    '行，您好好歇着，我一直在呢，想说话了就喊我。',
]


def opening(who='您'):
    return random.choice(_OPENINGS).format(who=who)


def topic_suggestion():
    """冷场 / 老人不知道聊什么时，给出一组话题选择（3 个类别，附一个具体问句）。"""
    picked = random.sample(TOPIC_GROUPS, 3)
    names = '、'.join(g['name'] for g in picked)
    first_prompt = picked[0]['prompts'][0]
    return {
        'reply': '要不咱们聊点轻松的？可以聊聊' + names + '。比如——' + first_prompt,
        'topics': picked,
    }


def silence_hint():
    return random.choice(_SILENCE_HINTS)


def closing():
    return random.choice(_CLOSINGS)


class CompanionSession:
    """一次陪伴通话的会话状态：opening → chatting → ending。"""

    def __init__(self):
        self.addressee = '您'
        self.stage = 'opening'
        self.silence_nudged = 0

    def set_addressee(self, value):
        self.addressee = {'grandma':'奶奶', 'grandpa':'爷爷', 'both':'爷爷奶奶'}.get(value, '您')

    def start(self):
        """开场暖场：返回问候 + 陪伴专用提示词（供前端注入大模型）。"""
        self.stage = 'chatting'
        return {
            'reply': opening(self.addressee),
            'prompt': COMPANION_SYSTEM_PROMPT + ' 当前交流对象称呼为' + self.addressee + '，必须保持一致，不得称呼为其他身份。',
            'stage': self.stage,
        }

    def on_topic_request(self):
        """老人不知道聊什么 → 提供话题选择。"""
        r = topic_suggestion()
        r['stage'] = self.stage
        return r

    def on_silence(self):
        """老人沉默 → 温和接话一次；之后安静陪着，不反复催促。"""
        if self.silence_nudged >= 1:
            return {'reply': '', 'stage': self.stage, 'quiet': True}
        self.silence_nudged += 1
        return {'reply': silence_hint(), 'stage': self.stage}

    def end(self):
        """自然结束：返回结束语，状态置为 ending。"""
        self.stage = 'ending'
        return {'reply': closing(), 'stage': self.stage, 'end': True}

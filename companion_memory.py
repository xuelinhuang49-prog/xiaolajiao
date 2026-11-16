"""P2.5: safe, selective context for natural conversational memory use."""
import re

def _norm(text):
    return re.sub(r"[\s，。！？?!、]", "", str(text or ""))

def companion_hint(latest_user, memories):
    """Only nudge the model when a saved preference is relevant to this turn.
    Does not perform actions, change memory, or replace empathetic responses.
    """
    if not isinstance(latest_user, str) or not memories:
        return ''
    q = _norm(latest_user)
    # Do not steer grief, distress, urgent symptoms or explicit refusal to entertainment.
    if re.search(r'难过|伤心|哭|疼|胸闷|喘不过气|摔倒|救命|去世|不想活|不想听|别放|不要放|不想聊|别提', q):
        return ''
    # Avoid diverting direct requests to the assistant's other functions.
    if re.search(r'打电话|视频通话|买东西|购物|提醒我|设置|播放|给我放|打开|关闭', q):
        return ''
    # A preference is relevant for light boredom / leisure conversation, not every greeting.
    if not re.search(r'无聊|没意思|没事干|闲着|打发时间|找点乐子|想找点事做', q):
        return ''
    audio = []
    for m in memories:
        fact = str(m.get('content', '')).strip()
        if re.fullmatch(r'(?:我|俺)(?:喜欢|爱)(?:听|看)(?:秦腔|京剧|豫剧|戏曲|评书|相声|音乐|歌曲)', fact):
            audio.append(fact)
    if not audio:
        return ''
    return ('\n【P2.5本轮轻度陪伴提示】\n'
            '老人正在表达无聊，已确认的相关爱好是：' + '；'.join(audio[:2]) + '。\n'
            '先自然回应当前感受；如果合适，可以用一句话轻轻提议聊聊或听听相关内容。'
            '不要声称已经播放，不要调用播放工具，不要把建议当成命令。'
            '若当前对话明确不想听或另有话题，就不要提这项爱好。\n')

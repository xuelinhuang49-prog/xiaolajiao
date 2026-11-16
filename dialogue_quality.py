"""P2.5.1: lightweight reply quality checks; no persistent memory writes."""
import re

def quality_hint(latest, messages, memories):
    if not isinstance(latest, str):
        return ''
    notes = ['【本轮对话质量检查】只把老人亲口陈述的事实当作事实；上一轮助手的猜测不是事实。'
             '老人纠正时立刻接受，不再重复质疑；避免机械复述，适合时只问一个贴近话题的问题。'
             '不要凭空判断好吃、开心或已经完成某件事。']
    if re.search(r'咸|淡|不好吃|太甜|太辣', latest):
        notes.append('老人正在评价食物口味：接受评价，不要建议让已经偏咸的食物再加盐。')
    if re.search(r'心情不好|心情不太好|有点难过|不开心|烦心', latest):
        notes.append('轻度负面情绪不代表自伤意图，不要说“想不开”“别想不开”等；先倾听再适度建议。')
    if re.search(r'包子|馅|早饭|早餐|吃了', latest):
        notes.append('早餐聊天不要推断“吃得香”“真好吃”，除非老人自己这么说。')
    if re.search(r'无聊|没意思|打发时间', latest):
        prefs = [str(m.get('content','')) for m in memories if isinstance(m, dict)]
        if any('喜欢听秦腔' in p for p in prefs) and not any('喜欢听京剧' in p for p in prefs):
            notes.append('本账号已确认爱好是秦腔，不是京剧；此前未确认或已取消的京剧修改不能覆盖秦腔。')
    return '\n' + '\n'.join(notes) + '\n'

def quality_issue(latest, reply, memories):
    if not isinstance(latest, str) or not isinstance(reply, str):
        return None
    if re.search(r'有点咸|太咸|咸了|偏咸', latest) and re.search(r'再加(?:点|些)?盐|多放(?:点|些)?盐|加盐', reply):
        return '老人已经明确表示食物偏咸，不能建议继续加盐。'
    if re.search(r'心情不好|心情不太好|有点难过|不开心', latest) and re.search(r'想不开|轻生', reply):
        return '老人只是表达情绪低落，不能无根据地推断轻生。'
    if re.search(r'包子|馅|早饭|早餐|吃了', latest) and not re.search(r'好吃|香|美味', latest) and re.search(r'真好吃|吃得挺香|一定很好吃', reply):
        return '老人没有说好吃，不能代替老人评价食物。'
    prefs = [str(m.get('content','')) for m in memories if isinstance(m, dict)]
    if re.search(r'无聊|没意思|打发时间', latest) and any('喜欢听秦腔' in p for p in prefs) and not any('喜欢听京剧' in p for p in prefs):
        if '京剧' in reply and '秦腔' not in reply:
            return '已确认爱好是秦腔，不能将历史中未确认的京剧当作已确认爱好。'
    return None

def safe_fallback(latest, memories, addressee):
    addr = {'grandma':'奶奶','grandpa':'爷爷','both':'爷爷奶奶'}.get(addressee,'奶奶')
    if re.search(r'有点咸|太咸|咸了|偏咸', latest):
        return '原来有点咸呀，难怪您觉得不好吃。下次做的时候可以少放点盐。'
    if re.search(r'心情不好|心情不太好|有点难过|不开心', latest):
        return '听起来今天心情不太好。您愿意和我说说怎么了吗？'
    if re.search(r'无聊|没意思|打发时间', latest):
        prefs = [str(m.get('content','')) for m in memories if isinstance(m, dict)]
        if any('喜欢听秦腔' in p for p in prefs):
            return '觉得有点无聊呀？要不要听段您喜欢的秦腔，或者咱们聊聊天？'
    if re.search(r'包子|馅|早饭|早餐|吃了', latest):
        return '听您说起早饭了。您觉得今天这顿吃得怎么样？'
    return '我听着呢，您再跟我说说。'

def polish_repeated_address(text, addressee):
    if not isinstance(text, str):
        return text
    addr = {'grandma':'奶奶','grandpa':'爷爷','both':'爷爷奶奶'}.get(addressee,'奶奶')
    # Only remove redundant vocatives at clause starts, never inside quoted memories.
    seen = False
    pieces = re.split(r'([，。！？!?；;])', text)
    for i, piece in enumerate(pieces):
        if i % 2:
            continue
        if piece.startswith(addr) and (len(piece)==len(addr) or piece[len(addr)] in '，,！!？? '):
            if seen:
                pieces[i] = re.sub('^'+re.escape(addr)+r'[，, ]*', '', piece, count=1)
                if not pieces[i] and i + 1 < len(pieces) and pieces[i + 1] in ('，', ','):
                    pieces[i + 1] = ''
            else:
                seen = True
    return ''.join(pieces)

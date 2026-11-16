"""P2.2 conservative, account-scoped retrieval for explicit personal-preference questions.
Only answers narrow, recognized questions. Other messages continue to Ollama.
"""
import re

def _category(content):
    s = str(content).replace(' ', '')
    if re.search(r'(喜欢|爱|爱好|偏好|常听|爱听|最爱听).{0,12}(秦腔|戏曲|音乐|歌曲|歌|评书|相声|京剧|豫剧)', s):
        return 'audio'
    if re.search(r'(秦腔|戏曲|音乐|歌曲|评书|相声|京剧|豫剧).{0,12}(喜欢|爱听)', s):
        return 'audio'
    if re.search(r'(喜欢|爱吃|最爱吃|爱).{0,12}(水果|苹果|梨|香蕉|橘子|橙子|葡萄|西瓜|桃|草莓|芒果)', s):
        return 'fruit'
    return None

def memory_answer(question, memories, addressee):
    if not isinstance(question, str): return None
    q = re.sub(r'[\s，。！？?!、]', '', question)
    # Do not hijack affirmative preference statements (e.g. '我喜欢吃梨').
    if not re.search(r'(什么|哪些|哪种|哪个|哪类|多少|几种|怎么|是否|是不是|吗|呢|[？?])', question):
        return None
    # Questions only; explicit current preferences and requests must follow normal conversation/tool path.
    if re.search(r'(不想|不要|不喜欢|播放|放一段|放点|给我放|现在想听|想吃)', q): return None
    category = None
    if re.search(r'(我|俺).{0,5}(喜欢|爱|平时).{0,6}(吃|什么水果)|喜欢吃什么水果|爱吃什么水果', q):
        category = 'fruit'
    elif re.search(r'(我|俺).{0,5}(喜欢|爱|平时).{0,6}(听|什么歌|什么戏)|喜欢听什么|爱听什么', q):
        category = 'audio'
    elif re.search(r'(记得|记住|还知道).{0,8}(我|俺).{0,5}(爱好|喜好|喜欢什么)', q):
        category = 'general'
    if category is None: return None
    found = [str(m.get('content','')).strip() for m in memories if _category(m.get('content','')) == category or category == 'general' and _category(m.get('content',''))]
    prefix = {'grandma':'奶奶','grandpa':'爷爷','both':'爷爷奶奶'}.get(addressee,'')
    if not found:
        what = {'fruit':'喜欢吃什么水果','audio':'平时喜欢听什么','general':'有哪些爱好'}[category]
        return f'{prefix}，这个我还不知道呢，您还没告诉我您{what}。'
    # Rephrase first-person stored facts into the elder's second-person perspective.
    # Do not rewrite arbitrary text beyond the leading subject of a confirmed memory.
    phrased = []
    for fact in found[:3]:
        if fact.startswith(('我喜欢', '俺喜欢')):
            phrased.append('您喜欢' + fact[3:])
        elif fact.startswith(('我爱', '俺爱')):
            phrased.append('您爱' + fact[2:])
        else:
            phrased.append('您之前告诉过我：' + fact)
    return f'{prefix}，我记得' + '；'.join(phrased) + '。'

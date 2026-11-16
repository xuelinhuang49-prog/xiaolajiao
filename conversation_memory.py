"""P2.3.1 conservative, consent-based preference memory for elder accounts."""
import re
import time
import threading
import auth_v4

_LOCK = threading.RLock()
_TTL = 600


def _init():
    with auth_v4.db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS memory_pending (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, content TEXT NOT NULL, created_at INTEGER NOT NULL)')

_init()


def _candidate(text):
    s = str(text or '').strip().strip('。！？!?,， ')
    if len(s) > 90 or len(s) < 4 or '\n' in s:
        return None
    # A question about a preference is not a new preference, even without a question mark.
    if re.search(r'(什么|哪些|哪种|哪个|哪类|多少|几种|怎么|是否|是不是|不喜欢|不爱|不想|以前|曾经|小时候|过去|假如|如果|他说|她说|听说|你喜欢|您喜欢|吗|呢|？|\?|别|不要|播放|放一段|帮我|请你|记住|忘记|删除|密码|身份证|住址|电话|银行卡|病|药|政治|宗教)', s):
        return None
    patterns = (
        r'^(?:奶奶|爷爷|小辣椒)[，, ]*(?:我|俺)(?:平时|一直|特别|最)?(?:喜欢|爱)(听|吃|喝|看)([\u4e00-\u9fff]{1,12})$',
        r'^(?:我|俺)(?:平时|一直|特别|最)?(?:喜欢|爱)(听|吃|喝|看)([\u4e00-\u9fff]{1,12})$',
    )
    for pattern in patterns:
        m = re.fullmatch(pattern, s)
        if m:
            action, obj = m.groups()
            if obj.endswith(('了', '吗', '呢')) or '不' in obj:
                return None
            return '我喜欢' + action + obj
    return None


def handle(user_id, text, addressee):
    """Return reply only when the conversational-memory flow owns this turn."""
    if not isinstance(text, str):
        return None
    s = re.sub(r'[\s，。！!？?、]', '', text)
    name = {'grandma':'奶奶','grandpa':'爷爷','both':'爷爷奶奶'}.get(addressee,'')
    yes = {'记住吧','记住','好呀记住吧','好的记住吧','好记住','可以记住','帮我记住','嗯记住吧','记下来吧','保存吧','好的保存吧'}
    no = {'不用记','别记','不要记','不记了','算了','不用了','取消','不保存','不用保存','先不记'}
    with _LOCK:
        with auth_v4.db() as con:
            row = con.execute('SELECT content,created_at FROM memory_pending WHERE user_id=?',(user_id,)).fetchone()
            if row and int(time.time())-row['created_at'] > _TTL:
                con.execute('DELETE FROM memory_pending WHERE user_id=?',(user_id,))
                row = None
            if row:
                if s in yes:
                    content = row['content']
                    existing = auth_v4.list_memories(user_id)
                    if content in [m['content'] for m in existing]:
                        con.execute('DELETE FROM memory_pending WHERE user_id=?',(user_id,))
                        return f'{name}，这件事我已经记住啦！'
                    # If saving fails, preserve pending so the user can retry.
                    try:
                        auth_v4.add_memory(user_id, content)
                    except ValueError:
                        return f'{name}，记忆暂时存不下了，您可以先到“我的记忆”里整理一下。'
                    con.execute('DELETE FROM memory_pending WHERE user_id=?',(user_id,))
                    return f'{name}，我记住啦！您喜欢{content.removeprefix("我喜欢")}。'
                if s in no:
                    con.execute('DELETE FROM memory_pending WHERE user_id=?',(user_id,))
                    return f'好的{name}，那我就不保存这件事啦。'
                # New topic: drop the stale confirmation; never treat later 'yes' as consent.
                con.execute('DELETE FROM memory_pending WHERE user_id=?',(user_id,))
            candidate = _candidate(text)
            if not candidate:
                return None
            if candidate in [m['content'] for m in auth_v4.list_memories(user_id)]:
                return None
            con.execute('INSERT OR REPLACE INTO memory_pending(user_id,content,created_at) VALUES(?,?,?)', (user_id,candidate,int(time.time())))
            return f'{name}，原来您{candidate.removeprefix("我")}呀！要不要我帮您记住？'

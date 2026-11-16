"""P2.4 conservative confirmed conversational memory update/delete/list.
Only explicitly matched requests are handled; other turns go to existing flows.
"""
import re
import time
import threading
import auth_v4

_LOCK = threading.RLock()
_TTL = 600

def _init():
    with auth_v4.db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS memory_change_pending (user_id INTEGER PRIMARY KEY, action TEXT NOT NULL, memory_id INTEGER NOT NULL, old_content TEXT NOT NULL, new_content TEXT, created_at INTEGER NOT NULL)')
_init()

def _clean(s):
    return re.sub(r'[\s，。！!？?、]', '', str(s or ''))

def _name(addressee):
    return {'grandma':'奶奶','grandpa':'爷爷','both':'爷爷奶奶'}.get(addressee, '您')

def _describe(content):
    s = content.strip()
    if s.startswith(('我','俺')):
        return '您' + s[1:]
    return s

def _find_exact(memories, action, item):
    target = '我喜欢' + action + item
    return [m for m in memories if _clean(m['content']) == _clean(target)]

def handle(user_id, text, addressee):
    if not isinstance(text,str): return None
    s = _clean(text)
    name = _name(addressee)
    yes = {'是的','对','确认','确定','好的','好','可以','同意','是','确认修改','确认删除','删吧','改吧','好呀','嗯','确定删除','确定修改'}
    no = {'不','不是','取消','算了','别改了','不改了','别删了','不删了','不要','不用了','先不改','先不删','不要修改','不要删除'}
    with _LOCK:
        with auth_v4.db() as con:
            row = con.execute('SELECT * FROM memory_change_pending WHERE user_id=?',(user_id,)).fetchone()
            if row and time.time()-row['created_at'] > _TTL:
                con.execute('DELETE FROM memory_change_pending WHERE user_id=?',(user_id,))
                row = None
            if row:
                if s in no:
                    con.execute('DELETE FROM memory_change_pending WHERE user_id=?',(user_id,))
                    return f'好的{name}，那就不改动您的记忆啦。'
                if s in yes:
                    current = next((m for m in auth_v4.list_memories(user_id) if m['id']==row['memory_id']),None)
                    if not current or current['content']!=row['old_content']:
                        con.execute('DELETE FROM memory_change_pending WHERE user_id=?',(user_id,))
                        return f'{name}，这条记忆已经发生变化了，我没有修改。请您重新告诉我。'
                    try:
                        if row['action']=='delete':
                            auth_v4.delete_memory(user_id,row['memory_id'])
                            reply=f'好的{name}，这条记忆已经删除啦。'
                        else:
                            auth_v4.update_memory(user_id,row['memory_id'],row['new_content'])
                            reply=f'好的{name}，已经改成“{_describe(row["new_content"])}”啦。'
                    except (ValueError,TypeError):
                        return f'{name}，这次没有修改成功，请稍后再试。'
                    con.execute('DELETE FROM memory_change_pending WHERE user_id=?',(user_id,))
                    return reply
                # Any unrelated turn cancels pending, so a later yes cannot accidentally mutate.
                con.execute('DELETE FROM memory_change_pending WHERE user_id=?',(user_id,))

            memories=auth_v4.list_memories(user_id)
            list_q = re.sub(r'^小辣椒', '', s)
            if list_q in {'你都记得我什么','你记得我什么','你都记得我什么呀','你记住了我什么','我的记忆有哪些','你记得我哪些事'}:
                if not memories: return f'{name}，我还没有保存您的个人记忆呢。'
                items='；'.join(_describe(m['content']) for m in memories[:10])
                tail='，其他记忆您可以在“我的记忆”里查看' if len(memories)>10 else ''
                return f'{name}，我记得：{items}{tail}。'

            # Delete must explicitly reference one uniquely identifiable confirmed preference.
            m=re.fullmatch(r'(?:请|帮我|小辣椒)?(?:把)?(?:我|俺)(?:喜欢|爱)(听|吃|喝|看)([\u4e00-\u9fff]{1,12}?)(?:这件事|这个喜好|这个偏好)?(?:忘了吧|忘掉吧|忘掉|忘记吧|忘记|删掉吧|删掉|删除吧|删除|别记了|不记了)',s)
            if m:
                action,item=m.groups()
                matches=_find_exact(memories,action,item)
                if len(matches)!=1:
                    return f'{name}，我没有找到唯一对应的记忆，您可以在“我的记忆”里查看。'
                target=matches[0]
                con.execute('INSERT OR REPLACE INTO memory_change_pending(user_id,action,memory_id,old_content,new_content,created_at) VALUES(?,?,?,?,?,?)',(user_id,'delete',target['id'],target['content'],None,int(time.time())))
                return f'{name}，您确定要删除“{_describe(target["content"])}”这条记忆吗？您说“确认”我再删除。'

            # Narrow correction: same action, one explicitly named old and new object.
            m=re.fullmatch(r'(?:我|俺)现在(?:更)?喜欢(听|吃|喝|看)([\u4e00-\u9fff]{1,12})[，,]?(?:不喜欢|不爱)(?:听|吃|喝|看)?([\u4e00-\u9fff]{1,12})了',s)
            if m:
                action,new_item,old_item=m.groups()
                if new_item==old_item: return None
                matches=_find_exact(memories,action,old_item)
                if len(matches)!=1:
                    return f'{name}，我没找到对应的旧记忆，暂时不会修改。您可以在“我的记忆”里查看。'
                target=matches[0]
                new_content='我喜欢'+action+new_item
                con.execute('INSERT OR REPLACE INTO memory_change_pending(user_id,action,memory_id,old_content,new_content,created_at) VALUES(?,?,?,?,?,?)',(user_id,'update',target['id'],target['content'],new_content,int(time.time())))
                return f'{name}，您是想把“{_describe(target["content"])}”改成“{_describe(new_content)}”吗？您说“确认”我再修改。'
    return None

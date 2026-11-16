"""Local V4 accounts. Password hashes and sessions are kept outside the source tree."""
import hashlib, hmac, json, os, secrets, sqlite3, threading, time
from pathlib import Path

DATA = Path(os.environ.get('XIAOLAJIAO_DATA_DIR', str(Path.home() / '.xiaolajiao_v4')))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'accounts.sqlite3'
_LOCK = threading.RLock()

def db():
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con

def init():
    with _LOCK, db() as con:
        con.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, pw_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN (\'elder\',\'family\')), addressee TEXT NOT NULL DEFAULT \'grandma\', created_at INTEGER NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, role TEXT NOT NULL CHECK(role IN (\'user\',\'assistant\')), content TEXT NOT NULL, created_at INTEGER NOT NULL)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id,id)')
        con.execute('CREATE TABLE IF NOT EXISTS user_nicknames (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, nickname TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS user_contacts (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL, PRIMARY KEY(user_id,name))')
        con.execute('CREATE TABLE IF NOT EXISTS elder_memories (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, content TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_memory_user ON elder_memories(user_id,id)')
        con.execute('CREATE TABLE IF NOT EXISTS user_reminders (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, when_at TEXT NOT NULL, content TEXT NOT NULL, notified INTEGER NOT NULL DEFAULT 0)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_reminder_user_due ON user_reminders(user_id,notified,when_at)')

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()

def public(row):
    return {'id': row['id'], 'username': row['username'], 'role': row['role'], 'addressee': row['addressee']}

def register(username, password, role, addressee):
    username = username.strip()
    if not 3 <= len(username) <= 32 or not all(c.isascii() and (c.isalnum() or c in '_-') for c in username):
        raise ValueError('账号需为3–32位英文字母、数字、下划线或连字符')
    if not 8 <= len(password) <= 128: raise ValueError('密码至少8位')
    if role not in ('elder', 'family'): raise ValueError('账号类型不正确')
    if addressee not in ('grandma', 'grandpa', 'both'): raise ValueError('称呼不正确')
    salt = secrets.token_hex(16)
    with _LOCK, db() as con:
        try:
            cur = con.execute('INSERT INTO users(username,salt,pw_hash,role,addressee,created_at) VALUES(?,?,?,?,?,?)', (username,salt,password_hash(password,salt),role,addressee,int(time.time())))
        except sqlite3.IntegrityError: raise ValueError('账号已存在')
        return cur.lastrowid

def login(username, password):
    with _LOCK, db() as con:
        row = con.execute('SELECT * FROM users WHERE username=?', (username.strip(),)).fetchone()
        dummy = password_hash(password, row['salt'] if row else '00'*16)
        if not row or not hmac.compare_digest(dummy, row['pw_hash']): return None
        token = secrets.token_urlsafe(32)
        con.execute('DELETE FROM sessions WHERE expires_at < ?', (int(time.time()),))
        con.execute('INSERT INTO sessions VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), row['id'], int(time.time())+86400*7))
        return token, public(row)

def user_for(token):
    if not token: return None
    with db() as con:
        row = con.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?', (hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        return public(row) if row else None

def logout(token):
    if token:
        with _LOCK, db() as con: con.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))

def set_addressee(user_id, value):
    if value not in ('grandma','grandpa','both'): raise ValueError('称呼不正确')
    with _LOCK, db() as con: con.execute('UPDATE users SET addressee=? WHERE id=?', (value,user_id))

def save_chat(user_id, role, content):
    if role not in ('user','assistant') or not isinstance(content,str) or len(content)>12000: raise ValueError('消息无效')
    with _LOCK, db() as con: con.execute('INSERT INTO chat_messages(user_id,role,content,created_at) VALUES(?,?,?,?)',(user_id,role,content,int(time.time())))

def chat_history(user_id, limit=100):
    with db() as con:
        rows = con.execute('SELECT role,content,created_at FROM (SELECT id,role,content,created_at FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT ?) ORDER BY id', (user_id,min(500,max(1,limit)))).fetchall()
        return [dict(r) for r in rows]
init()

# P2.1: Explicitly confirmed memories; never auto-extract from conversations.
def list_memories(user_id):
    with db() as con:
        return [dict(r) for r in con.execute('SELECT id,content,created_at,updated_at FROM elder_memories WHERE user_id=? ORDER BY id DESC LIMIT 50',(user_id,))]

def add_memory(user_id, content):
    if not isinstance(content,str): raise ValueError('记忆内容无效')
    content=content.strip()
    if not 2<=len(content)<=160: raise ValueError('记忆需为2至160个字')
    with _LOCK,db() as con:
        count=con.execute('SELECT COUNT(*) FROM elder_memories WHERE user_id=?',(user_id,)).fetchone()[0]
        if count>=50: raise ValueError('最多保存50条记忆，请先删除不需要的记忆')
        now=int(time.time())
        cur=con.execute('INSERT INTO elder_memories(user_id,content,created_at,updated_at) VALUES(?,?,?,?)',(user_id,content,now,now))
        return cur.lastrowid

def update_memory(user_id, memory_id, content):
    if not isinstance(content,str) or not 2<=len(content.strip())<=160: raise ValueError('记忆需为2至160个字')
    with _LOCK,db() as con:
        cur=con.execute('UPDATE elder_memories SET content=?,updated_at=? WHERE user_id=? AND id=?',(content.strip(),int(time.time()),user_id,int(memory_id)))
        if cur.rowcount!=1: raise ValueError('记忆不存在或无权限')

def delete_memory(user_id,memory_id):
    with _LOCK,db() as con:
        cur=con.execute('DELETE FROM elder_memories WHERE user_id=? AND id=?',(user_id,int(memory_id)))
        if cur.rowcount!=1: raise ValueError('记忆不存在或无权限')


def get_nickname(user_id):
    with db() as con:
        row=con.execute('SELECT nickname FROM user_nicknames WHERE user_id=?',(user_id,)).fetchone()
        return row['nickname'] if row else ''

def set_nickname(user_id, nickname):
    import re
    nickname=str(nickname or '').strip()
    if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9]{2,12}', nickname):
        raise ValueError('称呼需为2至12个汉字、字母或数字')
    with _LOCK, db() as con:
        con.execute('INSERT INTO user_nicknames(user_id,nickname) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET nickname=excluded.nickname',(user_id,nickname))
    return nickname

def list_contacts(user_id):
    with db() as con:
        rows=con.execute('SELECT name FROM user_contacts WHERE user_id=? ORDER BY name',(user_id,)).fetchall()
    return [{'name':'小辣椒','emoji':'🌶️','system':True}] + [{'name':r['name'],'emoji':'👤','system':False} for r in rows if r['name']!='小辣椒']

def change_contact(user_id,action,name):
    import re
    name=str(name or '').strip()
    if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9]{1,16}',name): raise ValueError('联系人姓名需为1至16个字')
    if name=='小辣椒': raise ValueError('小辣椒是系统联系人，不能修改或删除')
    with _LOCK,db() as con:
        if action=='add': con.execute('INSERT OR IGNORE INTO user_contacts(user_id,name) VALUES(?,?)',(user_id,name))
        elif action=='delete': con.execute('DELETE FROM user_contacts WHERE user_id=? AND name=?',(user_id,name))
        else: raise ValueError('操作无效')
    return list_contacts(user_id)


def list_reminders(user_id):
    with db() as con:
        rows=con.execute('SELECT id,when_at,content FROM user_reminders WHERE user_id=? AND notified=0 ORDER BY when_at',(user_id,)).fetchall()
    return [{'id':r['id'],'when':r['when_at'],'content':r['content']} for r in rows]

def add_reminder(user_id,when,content):
    from datetime import datetime
    when=str(when or '').strip();content=str(content or '').strip()
    try: dt=datetime.fromisoformat(when)
    except ValueError: raise ValueError('提醒时间格式不正确')
    if dt.tzinfo is not None: raise ValueError('请填写本地时间')
    if dt<=datetime.now(): raise ValueError('请选择未来的时间')
    if not 1<=len(content)<=100: raise ValueError('提醒内容需为1至100字')
    with _LOCK,db() as con:
        cur=con.execute('INSERT INTO user_reminders(user_id,when_at,content) VALUES(?,?,?)',(user_id,dt.isoformat(timespec='seconds'),content))
        return cur.lastrowid

def delete_reminder(user_id,reminder_id):
    with _LOCK,db() as con:
        cur=con.execute('DELETE FROM user_reminders WHERE user_id=? AND id=?',(user_id,int(reminder_id)))
        if cur.rowcount!=1: raise ValueError('未找到这条提醒')

def due_reminders(user_id):
    from datetime import datetime
    now=datetime.now().isoformat(timespec='seconds')
    with _LOCK,db() as con:
        rows=con.execute('SELECT id,content FROM user_reminders WHERE user_id=? AND notified=0 AND when_at<=? ORDER BY when_at',(user_id,now)).fetchall()
        if rows: con.executemany('UPDATE user_reminders SET notified=1 WHERE id=? AND user_id=?',[(r['id'],user_id) for r in rows])
    return [{'id':r['id'],'content':r['content']} for r in rows]

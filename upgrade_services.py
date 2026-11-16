"""P2.6: account-bound family links, avatar, WebRTC signaling, radio configuration.
This is a local development service, NOT a public deployment gateway.
"""
import json, os, secrets, sqlite3, subprocess, sys, time
from pathlib import Path
import auth_v4

RADIO_FILE = Path(__file__).with_name('radio_stations.json')

def connect():
    return auth_v4.db()

def init():
    with auth_v4._LOCK, connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS family_links (elder_id INTEGER NOT NULL, family_id INTEGER NOT NULL, label TEXT NOT NULL DEFAULT '家人', PRIMARY KEY(elder_id,family_id));
        CREATE TABLE IF NOT EXISTS family_profiles (user_id INTEGER PRIMARY KEY, display_name TEXT NOT NULL DEFAULT '家人', avatar TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS pairing_codes (code TEXT PRIMARY KEY, elder_id INTEGER NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, elder_id INTEGER NOT NULL, family_id INTEGER NOT NULL, caller_id INTEGER NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS call_signals (id INTEGER PRIMARY KEY, call_id TEXT NOT NULL, sender_id INTEGER NOT NULL, payload TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS call_signals_call ON call_signals(call_id,id);
        ''')
        cols={r['name'] for r in db.execute('PRAGMA table_info(calls)').fetchall()}
        for col in ('accepted_at','ended_at'):
            if col not in cols: db.execute(f'ALTER TABLE calls ADD COLUMN {col} INTEGER')
        if 'call_type' not in cols: db.execute("ALTER TABLE calls ADD COLUMN call_type TEXT NOT NULL DEFAULT 'video'")
init()

def need_role(user, role):
    if user['role'] != role: raise ValueError('当前账号类型不支持此操作')

def code(user):
    need_role(user,'elder')
    val = ''.join(str(secrets.randbelow(10)) for _ in range(6))
    with auth_v4._LOCK,connect() as db:
        db.execute('DELETE FROM pairing_codes WHERE elder_id=? OR expires<?',(user['id'],int(time.time())))
        db.execute('INSERT INTO pairing_codes VALUES(?,?,?)',(val,user['id'],int(time.time())+600))
    return {'code':val,'expires_seconds':600}

def bind(user, value):
    need_role(user,'family')
    with auth_v4._LOCK,connect() as db:
        row=db.execute('SELECT elder_id FROM pairing_codes WHERE code=? AND expires>?',(str(value).strip(),int(time.time()))).fetchone()
        if not row: raise ValueError('绑定码错误或已过期，请老人重新生成')
        db.execute('INSERT OR IGNORE INTO family_links(elder_id,family_id) VALUES(?,?)',(row['elder_id'],user['id']))
        db.execute('DELETE FROM pairing_codes WHERE code=?',(str(value).strip(),))
    return {'ok':True}

def profile(user, data):
    need_role(user,'family')
    name=str(data.get('name','')).strip()
    avatar=str(data.get('avatar',''))
    if not 1<=len(name)<=20: raise ValueError('称呼需要1至20个字符')
    if avatar and (not avatar.startswith('data:image/jpeg;base64,') or len(avatar)>450000):
        raise ValueError('头像处理失败，请重新选择照片')
    with auth_v4._LOCK,connect() as db:
        db.execute('INSERT INTO family_profiles VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name,avatar=excluded.avatar',(user['id'],name,avatar))
        db.execute('UPDATE family_links SET label=? WHERE family_id=?',(name,user['id']))
    return {'ok':True}

def family(user):
    with connect() as db:
        if user['role']=='elder':
            rows=db.execute('''SELECT l.family_id AS id, COALESCE(p.display_name,l.label) AS name,
              COALESCE(p.avatar,'') AS avatar, 'family' AS contact_type
              FROM family_links l LEFT JOIN family_profiles p ON p.user_id=l.family_id
              WHERE l.elder_id=? ORDER BY l.family_id''',(user['id'],)).fetchall()
        else:
            # 仅展示已绑定老人及与自己绑定同一位老人的家属；去重并排除本人。
            rows=db.execute('''SELECT id,name,avatar,contact_type FROM (
              SELECT l.elder_id AS id,u.username AS name,'' AS avatar,'elder' AS contact_type
                FROM family_links l JOIN users u ON u.id=l.elder_id WHERE l.family_id=?
              UNION
              SELECT sibling.family_id AS id,
                COALESCE(NULLIF(p.display_name,''),u.username) AS name,
                COALESCE(p.avatar,'') AS avatar,'family' AS contact_type
                FROM family_links mine JOIN family_links sibling ON sibling.elder_id=mine.elder_id
                JOIN users u ON u.id=sibling.family_id
                LEFT JOIN family_profiles p ON p.user_id=sibling.family_id
                WHERE mine.family_id=? AND sibling.family_id!=?
            ) ORDER BY contact_type DESC,id''',(user['id'],user['id'],user['id'])).fetchall()
        me=db.execute('SELECT display_name,avatar FROM family_profiles WHERE user_id=?',(user['id'],)).fetchone()
    return {'contacts':[dict(r) for r in rows], 'profile':dict(me) if me else {'display_name':'家人','avatar':''}}

def call_access(db,user,cid):
    row=db.execute('SELECT * FROM calls WHERE id=?',(str(cid),)).fetchone()
    if not row or user['id'] not in (row['elder_id'],row['family_id']): raise ValueError('无权访问此通话')
    return row

def start_call(user,other,call_type="video"):
    if call_type not in ("video","voice"): raise ValueError("不支持的通话类型")
    try: other=int(other)
    except (ValueError,TypeError): raise ValueError('联系人无效')
    if other==user['id']: raise ValueError('不能呼叫自己')
    with auth_v4._LOCK,connect() as db:
        target=db.execute('SELECT id,role FROM users WHERE id=?',(other,)).fetchone()
        if not target: raise ValueError('联系人不存在')
        if user['role']=='elder' and target['role']=='family':
            elder,fam=user['id'],other
            allowed=db.execute('SELECT 1 FROM family_links WHERE elder_id=? AND family_id=?',(elder,fam)).fetchone()
        elif user['role']=='family' and target['role']=='elder':
            elder,fam=other,user['id']
            allowed=db.execute('SELECT 1 FROM family_links WHERE elder_id=? AND family_id=?',(elder,fam)).fetchone()
        elif user['role']=='family' and target['role']=='family':
            # 两位家属必须至少共同绑定一位老人。复用现有通话表的两个参与者字段。
            elder,fam=user['id'],other
            allowed=db.execute('''SELECT 1 FROM family_links a JOIN family_links b
              ON a.elder_id=b.elder_id WHERE a.family_id=? AND b.family_id=? LIMIT 1''',(user['id'],other)).fetchone()
        else:
            raise ValueError('不支持的联系人类型')
        if not allowed: raise ValueError('对方不是您的家庭联系人')
        cid=secrets.token_urlsafe(18); now=int(time.time())
        db.execute('INSERT INTO calls(id,elder_id,family_id,caller_id,status,created,updated,call_type) VALUES(?,?,?,?,?,?,?,?)',(cid,elder,fam,user['id'],'ringing',now,now,call_type))
    return {'id':cid,'status':'ringing','call_type':call_type}

def calls(user):
    with connect() as db:
        rows=db.execute('SELECT id,elder_id,family_id,caller_id,status,created,accepted_at,ended_at,call_type FROM calls WHERE (elder_id=? OR family_id=?) AND status IN (\'ringing\',\'accepted\') AND created>? ORDER BY created DESC LIMIT 25',(user['id'],user['id'],int(time.time())-86400)).fetchall()
    return {'calls':[dict(r) for r in rows]}


def call_history(user, limit=100):
    limit=max(1,min(int(limit),200))
    with connect() as db:
        rows=db.execute('''SELECT c.id,c.elder_id,c.family_id,c.caller_id,c.status,c.created,c.accepted_at,c.ended_at,c.call_type,
          COALESCE(NULLIF(ep.display_name,''),eu.username) AS elder_name,
          COALESCE(NULLIF(fp.display_name,''),fu.username) AS family_name
          FROM calls c JOIN users eu ON eu.id=c.elder_id JOIN users fu ON fu.id=c.family_id
          LEFT JOIN family_profiles ep ON ep.user_id=c.elder_id
          LEFT JOIN family_profiles fp ON fp.user_id=c.family_id
          WHERE (c.elder_id=? OR c.family_id=?) AND c.status NOT IN ('ringing','accepted')
          ORDER BY c.created DESC LIMIT ?''',(user['id'],user['id'],limit)).fetchall()
    result=[]
    for row in rows:
        r=dict(row)
        r['other_name']=r['family_name'] if user['id']==r['elder_id'] else r['elder_name']
        r['direction']='outgoing' if r['caller_id']==user['id'] else 'incoming'
        r['duration_seconds']=max(0,(r['ended_at'] or r['accepted_at'])-r['accepted_at']) if r['accepted_at'] else 0
        result.append(r)
    return {'history':result}

def change_call(user,cid,status):
    if status not in ('accepted','rejected','ended'):raise ValueError('状态无效')
    with auth_v4._LOCK,connect() as db:
        row=call_access(db,user,cid)
        if status=='accepted' and (row['caller_id']==user['id'] or row['status']!='ringing'):raise ValueError('无法接听此来电')
        if status=='rejected' and (row['caller_id']==user['id'] or row['status']!='ringing'):raise ValueError('无法拒绝此来电')
        if status=='ended' and row['status'] in ('ended','rejected'):return {'ok':True}
        now=int(time.time())
        if status=='accepted': db.execute('UPDATE calls SET status=?,updated=?,accepted_at=COALESCE(accepted_at,?) WHERE id=?',(status,now,now,cid))
        else: db.execute('UPDATE calls SET status=?,updated=?,ended_at=COALESCE(ended_at,?) WHERE id=?',(status,now,now,cid))
    return {'ok':True}

def signal(user,cid,payload):
    raw=json.dumps(payload,ensure_ascii=False)
    if len(raw)>12000:raise ValueError('信令过大')
    with auth_v4._LOCK,connect() as db:
        row=call_access(db,user,cid)
        if row['status'] not in ('ringing','accepted'):raise ValueError('通话已结束')
        db.execute('INSERT INTO call_signals(call_id,sender_id,payload,created) VALUES(?,?,?,?)',(cid,user['id'],raw,int(time.time())))
    return {'ok':True}

def signals(user,cid,after):
    with connect() as db:
        call_access(db,user,cid)
        rows=db.execute('SELECT id,payload FROM call_signals WHERE call_id=? AND sender_id!=? AND id>? ORDER BY id LIMIT 100',(cid,user['id'],int(after))).fetchall()
    return {'signals':[{'id':r['id'],'payload':json.loads(r['payload'])} for r in rows]}

def stations():
    if not RADIO_FILE.exists():return {'stations':[]}
    return {'stations':json.loads(RADIO_FILE.read_text(encoding='utf8'))}

def qq_launch():
    if sys.platform!='win32':raise ValueError('QQ音乐启动功能仅支持 Windows')
    import winreg
    paths=[]
    for root in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for key in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\QQMusic.exe',):
            try:
                with winreg.OpenKey(root,key) as k:paths.append(winreg.QueryValueEx(k,'')[0])
            except OSError:pass
    for base in (os.environ.get('ProgramFiles(x86)',''),os.environ.get('ProgramFiles',''),os.environ.get('LOCALAPPDATA','')):
        if base:
            paths += [str(Path(base)/'Tencent'/'QQMusic'/'QQMusic.exe'),str(Path(base)/'QQMusic'/'QQMusic.exe')]
    for path in paths:
        if Path(path).is_file():
            subprocess.Popen([path],cwd=str(Path(path).parent),close_fds=True)
            return {'ok':True,'message':'已尝试启动QQ音乐'}
    raise ValueError('未找到QQ音乐安装位置，请确认已安装Windows客户端')

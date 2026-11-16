'use strict';
let currentCallType='video';
let me=null,active=null,pc=null,stream=null,last=0,poller=null,callStatus='',clock=null,clockStart=0,swapped=false,incomingCall=null,history=[];
let pendingIceCandidates=[];
let xljContacts=[];
let polling=false, pollGeneration=0;
/* 小辣椒 TURN 配置：将下面的占位符替换为你在 coturn 中设置的 TURN 用户密码（不是阿里云登录/root 密码）。 */
const XLJ_ICE_SERVERS = [
  {urls:'stun:stun.l.google.com:19302'},
  {urls:'turn:60.205.195.155:3478?transport=udp', username:'xiaolajiao', credential:'4328da09f3898734fb03b887d8de54f1032711cdf49a5b04'},
  {urls:'turn:60.205.195.155:3478?transport=tcp', username:'xiaolajiao', credential:'4328da09f3898734fb03b887d8de54f1032711cdf49a5b04'}
];
const $=id=>document.getElementById(id);
const XLJ_DEFAULT_AVATAR='data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22240%22%20height%3D%22240%22%20viewBox%3D%220%200%20240%20240%22%3E%3Crect%20width%3D%22240%22%20height%3D%22240%22%20rx%3D%22120%22%20fill%3D%22%23e8f1eb%22%2F%3E%3Ccircle%20cx%3D%22120%22%20cy%3D%2292%22%20r%3D%2243%22%20fill%3D%22%238bb6a0%22%2F%3E%3Cpath%20d%3D%22M42%20221c4-57%2034-83%2078-83s74%2026%2078%2083%22%20fill%3D%22%238bb6a0%22%2F%3E%3C%2Fsvg%3E';
let xljSelectedAvatar=null;
/* P2.8 foreground incoming ringtone: browser autoplay policy may require user gesture. */
/* P3.0 来电铃声：使用 Web Audio 合成，无需音频文件；设置仅保存在本机浏览器。 */
const P28Ring=(()=>{
  let ctx=null,timer=null,mode='',button=null;
  const key='xlj_ring_settings_v3';
  let settings={enabled:true,volume:65};
  try{settings={...settings,...JSON.parse(localStorage.getItem(key)||'{}')};}catch(e){}
  function save(){try{localStorage.setItem(key,JSON.stringify(settings));}catch(e){}}
  function unlock(){try{ctx=ctx||new (window.AudioContext||window.webkitAudioContext)();if(ctx.state==='suspended')ctx.resume().catch(()=>{});}catch(e){}}
  function tone(freq,start,duration,level){if(!ctx||ctx.state!=='running')return;const osc=ctx.createOscillator(),gain=ctx.createGain();osc.type='sine';osc.frequency.value=freq;gain.gain.setValueAtTime(.0001,start);gain.gain.exponentialRampToValueAtTime(Math.max(.0002,level),start+.025);gain.gain.exponentialRampToValueAtTime(.0001,start+duration);osc.connect(gain).connect(ctx.destination);osc.start(start);osc.stop(start+duration+.03);}
  function play(){if(!settings.enabled||!ctx||ctx.state!=='running')return;const t=ctx.currentTime+.015,v=Math.min(1,Math.max(0,Number(settings.volume)/100));if(mode==='incoming'){for(const [offset,freq] of [[0,523.25],[.24,659.25],[.48,783.99],[.75,659.25]])tone(freq,t+offset,.22,v*.12);}else if(mode==='outgoing'){tone(440,t,.18,v*.07);tone(554.37,t+.22,.18,v*.07);}}
  function stop(){if(timer)clearInterval(timer);timer=null;mode='';}
  function start(kind='incoming'){if(mode===kind&&timer)return;stop();mode=kind;unlock();play();timer=setInterval(play,kind==='incoming'?2400:2900);}
  function settingsButton(){if(button)return;button=document.createElement('button');button.type='button';button.textContent='🔔 铃声设置';button.style.cssText='display:block;margin:12px auto;padding:11px 16px;border:1px solid #ddd;border-radius:12px;background:#fff;color:#333;font-size:15px;cursor:pointer;';button.onclick=()=>{
    const overlay=document.createElement('div');overlay.style.cssText='position:fixed;inset:0;background:#0008;z-index:2147483647;display:flex;align-items:center;justify-content:center;padding:20px;';
    const card=document.createElement('div');card.style.cssText='width:min(100%,350px);background:white;color:#222;border-radius:18px;padding:22px;font:16px system-ui;box-shadow:0 10px 40px #0003;';
    const title=document.createElement('h2');title.textContent='🔔 小辣椒铃声设置';title.style.margin='0 0 16px';
    const label=document.createElement('label');label.style.cssText='display:flex;align-items:center;gap:10px;margin-bottom:18px';const check=document.createElement('input');check.type='checkbox';check.checked=settings.enabled;label.append(check,document.createTextNode('开启来电与拨号铃声'));
    const vol=document.createElement('input');vol.type='range';vol.min='0';vol.max='100';vol.value=settings.volume;vol.style.width='100%';const vlabel=document.createElement('p');vlabel.textContent='铃声音量：'+settings.volume+'%';vol.oninput=()=>{vlabel.textContent='铃声音量：'+vol.value+'%';};
    const actions=document.createElement('div');actions.style.cssText='display:flex;gap:10px;margin-top:18px;';
    const preview=document.createElement('button');preview.textContent='▶ 试听';const done=document.createElement('button');done.textContent='保存并关闭';for(const b of [preview,done])b.style.cssText='flex:1;padding:12px 8px;border:0;border-radius:10px;background:#f1eee9;color:#222;font-size:15px';
    preview.onclick=()=>{settings.enabled=check.checked;settings.volume=Number(vol.value);stop();start('incoming');setTimeout(()=>{if(mode==='incoming')stop();},1800);};
    done.onclick=()=>{settings.enabled=check.checked;settings.volume=Number(vol.value);save();stop();overlay.remove();};
    actions.append(preview,done);card.append(title,label,vlabel,vol,actions);overlay.append(card);overlay.onclick=e=>{if(e.target===overlay){stop();overlay.remove();}};document.body.append(overlay);
  };return button;}
  return{unlock,start,stop,settingsButton};
})();
document.addEventListener('pointerdown',()=>P28Ring.unlock(),{passive:true});

async function req(path,method='GET',data){const r=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||'操作失败');return j;}
function toast(t){const x=$('toast');x.textContent=t;x.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>x.classList.remove('show'),3500);}
async function run(fn){try{await fn();}catch(e){toast(e.message);}}
async function register(){run(async()=>{await req('/api/auth/register','POST',{username:$('username').value,password:$('password').value,role:'family',addressee:'grandma'});toast('注册成功，请登录');});}
async function login(){run(async()=>{const d=await req('/api/auth/login','POST',{username:$('username').value,password:$('password').value});if(d.user.role!=='family')throw Error('请使用子女账号登录');await ready();});}
async function ready(){const d=await req('/api/auth/me');me=d.user;if(me.role!=='family')return;$('auth').hidden=true;$('app').hidden=false;await refresh();navigate('home');$('meView').append(P28Ring.settingsButton());await loadCare(true);startCarePoll();}
async function logout(){await endCall();await req('/api/auth/logout','POST',{});location.reload();}
function navigate(name){if(active){toast('请先结束通话');return;}for(const n of ['home','care','history','me'])$(n+'View').hidden=n!==name;document.querySelectorAll('.bottom-nav button').forEach(b=>b.classList.toggle('selected',b.dataset.view===name));$('pageTitle').textContent=({home:'家人，常联系',care:'今日照护',history:'通话记录',me:'我的家庭'})[name];if(name==='history')loadHistory();if(name==='care')loadCare();}
function resize(file){return new Promise((resolve,reject)=>{const img=new Image(),url=URL.createObjectURL(file);img.onload=()=>{try{const c=document.createElement('canvas');c.width=c.height=240;const ctx=c.getContext('2d');const side=Math.min(img.width,img.height);ctx.drawImage(img,(img.width-side)/2,(img.height-side)/2,side,side,0,0,240,240);resolve(c.toDataURL('image/jpeg',.76));}catch(e){reject(Error('照片处理失败，请换一张重试'));}finally{URL.revokeObjectURL(url);}};img.onerror=()=>{URL.revokeObjectURL(url);reject(Error('当前浏览器无法读取这张照片，请尝试使用 JPG 格式'));};img.src=url;});}
async function saveProfile(){run(async()=>{const f=$('photo').files[0];let avatar=xljSelectedAvatar||$('preview').dataset.avatar||'';if(!xljSelectedAvatar&&f)avatar=await resize(f);await req('/api/upgrade/profile','POST',{name:$('displayName').value.trim(),avatar});xljSelectedAvatar=null;$('photo').value='';toast('资料已保存');await refresh();});}
$('photo').addEventListener('change',async()=>{const file=$('photo').files[0];if(!file)return;try{if(!file.type.startsWith('image/'))throw Error('请选择照片文件');xljSelectedAvatar=await resize(file);$('preview').src=xljSelectedAvatar;toast('已选择照片，请点击保存个人资料');}catch(e){xljSelectedAvatar=null;toast(e.message);}});
async function bind(){run(async()=>{await req('/api/upgrade/bind','POST',{code:$('pairCode').value.trim()});$('pairCode').value='';$('bindDetails').open=false;toast('绑定成功，以后无需重复绑定');await refresh();navigate('home');$('meView').append(P28Ring.settingsButton());});}
/* P3.6 联系人备注：以登录账号和联系人 ID 为键，仅在当前浏览器保存。 */
function xljRemarkKey(id){return 'xlj_contact_remark_v1_'+String(me?.id||'unknown')+'_'+String(id);}
function xljContactName(p){try{return localStorage.getItem(xljRemarkKey(p.id))||p.name;}catch(e){return p.name;}}
function xljEditRemark(p){
  const current=xljContactName(p);
  const value=window.prompt('给 '+p.name+' 设置联系人备注（留空恢复原名称）',current===p.name?'':current);
  if(value===null)return;
  const name=value.trim();
  if(name.length>20){toast('备注不能超过20个字');return;}
  try{if(name)localStorage.setItem(xljRemarkKey(p.id),name);else localStorage.removeItem(xljRemarkKey(p.id));}
  catch(e){toast('浏览器未允许保存备注');return;}
  refresh().then(()=>toast(name?'联系人备注已保存':'已恢复原名称')).catch(e=>toast(e.message));
}
function elderCard(p){
  const c=document.createElement('div');c.className='elder-card';
  const icon=document.createElement('div');icon.className='elder-icon';
  if(p.contact_type==='family'&&p.avatar){const img=document.createElement('img');img.src=p.avatar;img.alt=xljContactName(p)+'的头像';img.style.cssText='width:100%;height:100%;object-fit:cover;border-radius:50%';icon.append(img);}
  else icon.textContent=p.contact_type==='family'?'👨‍👩‍👧':'👵';
  const info=document.createElement('div');info.className='elder-info';
  const name=document.createElement('b');name.textContent=xljContactName(p);
  const hint=document.createElement('small');hint.textContent=p.contact_type==='family'?'家庭成员 · 可语音或视频联系':'已绑定老人 · 随时联系';
  info.append(name,hint);const button=document.createElement('button');button.textContent='📞 联系'+xljContactName(p);
  button.onclick=()=>chooseCall(p.id,xljContactName(p));const edit=document.createElement('button');edit.type='button';edit.textContent='✏️ 修改备注';edit.style.cssText='margin-top:8px;background:#f1f6f2;color:#27674c;border:1px solid #c9d9cf;border-radius:10px;padding:9px 12px;font-size:14px';edit.onclick=()=>xljEditRemark(p);c.append(icon,info,button,edit);return c;
}
async function refresh(){const d=await req('/api/upgrade/family');xljContacts=d.contacts||[];$('displayName').value=d.profile.display_name||'家人';$('preview').dataset.avatar=d.profile.avatar||'';if(!xljSelectedAvatar)$('preview').src=d.profile.avatar||XLJ_DEFAULT_AVATAR;$('homeElders').replaceChildren();$('boundList').replaceChildren();$('homeUnbound').hidden=d.contacts.length>0;for(const p of d.contacts){$('homeElders').append(elderCard(p));const item=document.createElement('p');item.textContent=(p.contact_type==='family'?'✓ 家庭成员：':'✓ 已绑定老人：')+xljContactName(p);$('boundList').append(item);}if(!d.contacts.length)$('boundList').textContent='尚未绑定老人账号';await loadHistory();}
function historyCard(c){const item=document.createElement('div');item.className='history-item';const icon=document.createElement('div');icon.className='history-icon';icon.textContent=c.direction==='outgoing'?'↗':'↙';const info=document.createElement('div');info.className='history-info';const title=document.createElement('b');const otherId=c.elder_id===me.id?c.family_id:c.elder_id;const contact=xljContacts.find(p=>p.id===otherId);title.textContent=(c.direction==='outgoing'?'呼叫 ':'来自 ')+(contact?xljContactName(contact):c.other_name);const sub=document.createElement('small');sub.textContent=new Date(c.created*1000).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});info.append(title,sub);const dur=document.createElement('div');dur.className='duration';dur.textContent=c.accepted_at?(Math.floor(c.duration_seconds/60)+'分'+String(c.duration_seconds%60).padStart(2,'0')+'秒'):(c.status==='rejected'?'已拒接':'未接通');item.append(icon,info,dur);return item;}
async function loadHistory(){try{const d=await req('/api/upgrade/call-history');history=d.history;for(const [id,items] of [['recentHistory',history.slice(0,3)],['allHistory',history]]){const box=$(id);box.replaceChildren();if(!items.length){const p=document.createElement('p');p.className='empty';p.textContent='暂无历史通话';box.append(p);}else for(const c of items)box.append(historyCard(c));}}catch(e){toast('通话记录暂时无法加载：'+e.message);}}
function chooseCall(id,name){const modal=$('p28Choose');$('p28ChooseName').textContent='联系 '+name;modal.hidden=false;$('p28Video').onclick=()=>{modal.hidden=true;run(()=>startCall(id,name,'video'));};$('p28Voice').onclick=()=>{modal.hidden=true;run(()=>startCall(id,name,'voice'));};}
function applyCallType(){const voice=currentCallType==='voice';$('callPanel').classList.toggle('voice-call',voice);$('cameraBtn').hidden=voice;$('flipBtn').hidden=voice;$('swapVideo').hidden=voice;$('mainVideoLabel').textContent=voice?'语音通话':$('callTitle').textContent;}
function showCall(name){swapped=false;$('callPanel').classList.remove('swapped');$('callPanel').hidden=false;$('callTitle').textContent=name;$('callStatus').textContent='正在呼叫…';$('callTimer').textContent='00:00';$('mainVideoLabel').textContent=name;applyCallType();}
function swapVideos(){swapped=!swapped;$('callPanel').classList.toggle('swapped',swapped);$('mainVideoLabel').textContent=swapped?'我':$('callTitle').textContent;}
function startClock(){if(clock)return;clockStart=Date.now();clock=setInterval(()=>{const sec=Math.floor((Date.now()-clockStart)/1000);$('callTimer').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');},1000);}
async function setup(){if(pc)return;stream=await navigator.mediaDevices.getUserMedia({video:currentCallType==='video',audio:true});pc=new RTCPeerConnection({iceServers:XLJ_ICE_SERVERS});stream.getTracks().forEach(t=>pc.addTrack(t,stream));$('local').srcObject=stream;pc.ontrack=e=>{$('remote').srcObject=e.streams[0];};pc.onicecandidate=e=>{if(e.candidate)send({candidate:e.candidate}).catch(console.error);};pc.onconnectionstatechange=()=>{if(!pc)return;console.info('[小辣椒RTC/子女] connectionState:',pc.connectionState,'ice:',pc.iceConnectionState);if(pc.connectionState==='connected'){P28Ring.stop();$('callStatus').textContent='正在通话';startClock();}else if(pc.connectionState==='disconnected')$('callStatus').textContent='连接暂时中断…';else if(pc.connectionState==='failed'){P28Ring.stop();$('callStatus').textContent='音视频连接失败：请检查 ICE/TURN';}};pc.oniceconnectionstatechange=()=>console.info('[小辣椒RTC/子女] ICE:',pc?.iceConnectionState);}
async function send(payload){if(active)await req('/api/upgrade/signal','POST',{id:active,payload});}
async function startCall(id,name,type='video'){currentCallType=type;const c=await req('/api/upgrade/call','POST',{target:id,call_type:type});active=c.id;pollGeneration++;pendingIceCandidates=[];last=0;callStatus='ringing';showCall(name);P28Ring.start('outgoing');poller=setInterval(poll,1600);}
async function answer(c){P28Ring.stop();currentCallType=c.call_type||'video';active=c.id;pollGeneration++;pendingIceCandidates=[];last=0;callStatus='accepted';P28Ring.stop();showCall('家人来电');$('callStatus').textContent='正在建立连接…';try{await setup();await req('/api/upgrade/call-status','POST',{id:active,status:'accepted'});poller=setInterval(poll,1600);}catch(e){await endCall();throw e;}}
async function handle(p){if(p.description){await setup();await pc.setRemoteDescription(p.description);for(const candidate of pendingIceCandidates.splice(0)){try{await pc.addIceCandidate(candidate);}catch(e){console.warn('ICE候选添加失败',e);}}if(p.description.type==='offer'){const a=await pc.createAnswer();await pc.setLocalDescription(a);await send({description:pc.localDescription});}}else if(p.candidate){if(!pc||!pc.remoteDescription){pendingIceCandidates.push(p.candidate);}else{try{await pc.addIceCandidate(p.candidate);}catch(e){console.warn('ICE候选添加失败',e);}}}}
async function poll(){if(!active||polling)return;polling=true;const generation=pollGeneration;try{const d=await req('/api/upgrade/calls');const c=d.calls.find(x=>x.id===active);if(!c||['ended','rejected'].includes(c.status)){await endCall(false);toast('通话已结束');return;}if(c.status==='accepted'&&callStatus!=='accepted'){P28Ring.stop();callStatus='accepted';$('callStatus').textContent='正在建立视频连接…';if(c.caller_id===me.id){await setup();const offer=await pc.createOffer();await pc.setLocalDescription(offer);await send({description:pc.localDescription});}}const s=await req('/api/upgrade/signals?id='+encodeURIComponent(active)+'&after='+last);for(const x of s.signals){if(generation!==pollGeneration||!active)break;await handle(x.payload);last=x.id;}}catch(e){console.error('[小辣椒RTC/子女] 信令处理失败',e);toast('通话连接异常：'+e.message);}finally{polling=false;}}
async function endCall(sendEnd=true){P28Ring.stop();const id=active;active=null;pollGeneration++;pendingIceCandidates=[];clearInterval(poller);poller=null;clearInterval(clock);clock=null;if(sendEnd&&id)try{await req('/api/upgrade/call-status','POST',{id,status:'ended'});}catch(e){}if(pc){pc.close();pc=null;}if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}$('remote').srcObject=null;$('local').srcObject=null;$('callPanel').hidden=true;callStatus='';if(me)await loadHistory();}
function toggleMute(){if(!stream)return;const track=stream.getAudioTracks()[0];if(track){track.enabled=!track.enabled;$('muteBtn').innerHTML=track.enabled?'<span>🎙</span>静音':'<span>🔇</span>取消静音';}}
function toggleCamera(){if(!stream)return;const track=stream.getVideoTracks()[0];if(track){track.enabled=!track.enabled;$('cameraBtn').innerHTML=track.enabled?'<span>📷</span>关闭摄像头':'<span>🚫</span>打开摄像头';}}
async function flipCamera(){if(!stream||!pc)return;const old=stream.getVideoTracks()[0];const mode=old?.getSettings().facingMode==='environment'?'user':'environment';try{const next=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:mode}},audio:false});const track=next.getVideoTracks()[0];const sender=pc.getSenders().find(s=>s.track?.kind==='video');if(sender)await sender.replaceTrack(track);stream.removeTrack(old);stream.addTrack(track);old.stop();$('local').srcObject=stream;}catch(e){toast('摄像头切换失败：'+e.message);}}
async function incoming(){if(!me||active)return;try{const d=await req('/api/upgrade/calls');const c=d.calls.find(x=>x.status==='ringing'&&x.caller_id!==me.id);if(incomingCall){if(!c||c.id!==incomingCall.id){incomingCall=null;$('incomingPanel').hidden=true;P28Ring.stop();}return;}if(c){P28Ring.stop();incomingCall=c;const caller=xljContacts.find(p=>p.id===c.caller_id);$('incomingType').textContent=(caller?xljContactName(caller)+' · ':'家人 · ')+(c.call_type==='voice'?'语音来电':'视频来电');$('incomingPanel').hidden=false;P28Ring.start();}}catch(e){console.warn(e);}}
async function acceptIncoming(){P28Ring.stop();const c=incomingCall;incomingCall=null;$('incomingPanel').hidden=true;if(c)run(()=>answer(c));}
async function rejectIncoming(){P28Ring.stop();const c=incomingCall;incomingCall=null;$('incomingPanel').hidden=true;if(c)run(()=>req('/api/upgrade/call-status','POST',{id:c.id,status:'rejected'}));}
/* P3.0 今日照护：只读动态。独立锁与定时器，绝不复用 WebRTC 的 polling / poller，也不调用 refresh()。 */
let careLoading=false,carePollTimer=null;
const CARE_STATUS_LABEL={responded:'已回应',snoozed:'已回应 · 稍后提醒',waiting:'等待回应',no_response:'暂无回应'};
async function loadCare(quiet){
  if(careLoading)return;
  careLoading=true;
  try{
    const d=await req('/api/care/feed');
    renderCare(d);
    const s=d.summary||{};
    $('careHomeTotal').textContent=String(s.total||0);
    $('careHomeWaiting').textContent=String((s.waiting||0)+(s.snoozed||0));
    $('careHomeMissed').textContent=String(s.no_response||0);
  }catch(e){
    if(!quiet)toast('今日照护暂时无法加载：'+e.message);
  }finally{
    careLoading=false;
  }
}
function careChip(label,count,cls){
  const chip=document.createElement('div');chip.className='care-chip '+(cls||'');
  const b=document.createElement('b');b.textContent=String(count||0);
  const small=document.createElement('span');small.textContent=label;
  chip.append(b,small);return chip;
}
function renderCare(d){
  const summary=$('careSummary');summary.replaceChildren();
  const s=d.summary||{};
  summary.append(careChip('已回应',s.responded,'ok'),careChip('稍后提醒',s.snoozed,'wait'),
    careChip('等待回应',s.waiting,'wait'),careChip('暂无回应',s.no_response,'miss'));
  $('careUnbound').hidden=!d.unbound;
  const box=$('careFeed');box.replaceChildren();
  for(const e of d.elders||[]){
    const card=document.createElement('div');card.className='card care-person';
    const head=document.createElement('div');head.className='care-person-head';
    const avatar=document.createElement('div');avatar.className='care-avatar';avatar.textContent='👵';
    const info=document.createElement('div');info.className='care-person-info';
    const name=document.createElement('b');name.textContent=e.name||e.username||'家人';
    const meta=document.createElement('small');
    meta.textContent=(e.enabled?'主动关怀已开启':'主动关怀已关闭')+' · 今日 '+(e.summary.total||0)+' 条';
    info.append(name,meta);
    const call=document.createElement('button');call.className='light care-call';call.textContent='📞 打电话';
    call.onclick=()=>run(()=>startCall(e.id,e.name||e.username,'voice'));
    head.append(avatar,info,call);card.append(head);

    if(!e.events||!e.events.length){
      const p=document.createElement('p');p.className='empty care-empty';p.textContent='今天还没有照护记录';
      card.append(p);
    }else{
      const list=document.createElement('div');list.className='care-events';
      for(const ev of e.events){
        const row=document.createElement('div');row.className='care-event';
        const time=document.createElement('span');time.className='care-event-time';time.textContent=ev.time||'';
        const body=document.createElement('div');body.className='care-event-body';
        const title=document.createElement('b');title.textContent=ev.title||'';
        if(ev.demo){const badge=document.createElement('span');badge.className='care-demo-badge';badge.textContent='演示';title.append(badge);}
        const sub=document.createElement('small');sub.textContent=ev.body||'';
        body.append(title,sub);
        const pill=document.createElement('span');pill.className='care-status '+ev.status;
        pill.textContent=CARE_STATUS_LABEL[ev.status]||'';
        row.append(time,body,pill);list.append(row);
      }
      card.append(list);
    }
    box.append(card);
  }
}
function startCarePoll(){
  clearInterval(carePollTimer);
  carePollTimer=setInterval(()=>{
    if(document.hidden||active)return;
    const onCare=!$('careView').hidden,onHome=!$('homeView').hidden;
    if(!onCare&&!onHome)return;
    loadCare(true);
  },60000);
}
setInterval(incoming,2500);document.addEventListener('visibilitychange',()=>{if(!document.hidden){incoming();if(me){const onCare=!$('careView').hidden,onHome=!$('homeView').hidden;if(onCare||onHome)loadCare(true);}}});req('/api/auth/me').then(d=>{if(d.user?.role==='family')ready();}).catch(()=>{});

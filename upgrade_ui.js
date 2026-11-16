/* P2.6 enhancement: family contacts, streaming radio, local media, QQMusic, WebRTC call. */
(()=>{
'use strict';

/* P3.3: 使用用户提供的真人语音 MP3 作为老人端来电铃声。 */
const P28Ring=(()=>{
  const KEY='xlj_ring_settings_v3';
  let settings={enabled:true,volume:75};
  try{settings={...settings,...JSON.parse(localStorage.getItem(KEY)||'{}')};}catch(e){}
  let audio=null,ctx=null,timer=null,mode='',previewTimer=null;
  const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(settings));}catch(e){}};
  function getAudio(){
    if(!audio){audio=new Audio('/xlj_incoming_call.mp3');audio.preload='auto';audio.loop=true;
      audio.addEventListener('error',()=>console.error('[小辣椒铃声] MP3 加载失败：请检查 /xlj_incoming_call.mp3 是否返回音频文件'));}
    audio.volume=Math.max(0,Math.min(1,Number(settings.volume)/100));return audio;
  }
  function unlock(){try{if(!ctx)ctx=new (window.AudioContext||window.webkitAudioContext)();if(ctx.state==='suspended')return ctx.resume().catch(()=>{});}catch(e){}return Promise.resolve();}
  function beep(){if(!ctx||ctx.state!=='running'||!settings.enabled)return;const t=ctx.currentTime;for(const [freq,delay] of [[440,0],[520,.22]]){const osc=ctx.createOscillator(),g=ctx.createGain();osc.frequency.value=freq;g.gain.setValueAtTime(.0001,t+delay);g.gain.exponentialRampToValueAtTime(Math.max(.001,settings.volume/100*.10),t+delay+.02);g.gain.exponentialRampToValueAtTime(.0001,t+delay+.18);osc.connect(g).connect(ctx.destination);osc.start(t+delay);osc.stop(t+delay+.2);}}
  function stop(){mode='';if(timer)clearInterval(timer);timer=null;if(previewTimer)clearTimeout(previewTimer);previewTimer=null;if(audio){audio.pause();audio.currentTime=0;}}
  async function start(kind='incoming'){
    if(mode===kind)return;stop();mode=kind;
    if(!settings.enabled||Number(settings.volume)<=0)return;
    if(kind==='incoming'){
      try{const a=getAudio();a.currentTime=0;await a.play();}catch(e){console.warn('[小辣椒铃声] MP3 播放失败',e);}
    }else{await unlock();beep();timer=setInterval(beep,2900);}
  }
  async function enableIncoming(){settings.enabled=true;settings.volume=Math.max(75,Number(settings.volume)||0);save();stop();await start('incoming');}
  function settingsButton(){const b=document.createElement('button');b.type='button';b.textContent='🔔 铃声设置';b.style.cssText='padding:12px 18px;border-radius:12px;font-size:18px;';b.onclick=()=>{
    const overlay=document.createElement('div');overlay.style.cssText='position:fixed;inset:0;background:#0009;z-index:2147483647;display:flex;align-items:center;justify-content:center;padding:20px';
    const card=document.createElement('div');card.style.cssText='background:#fff;color:#222;border-radius:18px;padding:24px;width:min(100%,380px);font:18px system-ui';
    const title=document.createElement('h2');title.textContent='🔔 来电铃声设置';
    const label=document.createElement('label');label.textContent='启用来电铃声 ';const ck=document.createElement('input');ck.type='checkbox';ck.checked=settings.enabled;label.append(ck);
    const desc=document.createElement('p');desc.textContent='铃声：姥，来电话了（真人语音）';
    const vl=document.createElement('p');vl.textContent='音量：'+settings.volume+'%';const range=document.createElement('input');range.type='range';range.min='0';range.max='100';range.value=settings.volume;range.style.width='100%';range.oninput=()=>{vl.textContent='音量：'+range.value+'%';if(audio)audio.volume=Number(range.value)/100;};
    const preview=document.createElement('button');preview.textContent='▶ 试听铃声';preview.style.cssText='padding:12px;margin:10px';preview.onclick=async()=>{settings.enabled=ck.checked;settings.volume=Number(range.value);save();stop();await start('incoming');previewTimer=setTimeout(()=>{if(mode==='incoming')stop();},12500);};
    const done=document.createElement('button');done.textContent='保存并关闭';done.style.cssText='padding:12px;margin:10px';done.onclick=()=>{settings.enabled=ck.checked;settings.volume=Number(range.value);save();stop();overlay.remove();};
    card.append(title,label,desc,vl,range,preview,done);overlay.append(card);overlay.onclick=e=>{if(e.target===overlay){stop();overlay.remove();}};document.body.append(overlay);
  };return b;}
  return{unlock,start,stop,settingsButton,enableIncoming,diagnose(){return {state:audio?(audio.paused?'paused':'playing'):'not-created',enabled:settings.enabled,volume:settings.volume};}};
})();
document.addEventListener('pointerdown',()=>P28Ring.unlock(),{passive:true});
// 浏览器可能阻止非用户手势触发的来电声音。提供可见的启用入口。
function xljEnableIncomingSound(){
  P28Ring.unlock();
  const hint=document.getElementById('xljSoundReady');
  if(hint)hint.textContent='✓ 已尝试启用来电铃声（请用试听确认）';
}
function xljSoundEnableButton(){
  const wrap=document.createElement('div');wrap.style.cssText='margin:12px 0;text-align:center';
  const b=document.createElement('button');b.type='button';b.textContent='🔔 开启来电铃声';
  b.style.cssText='font-size:18px;padding:13px 20px;border-radius:12px;border:1px solid #e0a74e;background:#fff5d9;color:#5d410e;cursor:pointer;';
  b.onclick=xljEnableIncomingSound;
  const hint=document.createElement('p');hint.id='xljSoundReady';hint.style.cssText='font-size:13px;margin:7px 0;color:#655';hint.textContent='首次使用请点击一次，确保浏览器允许播放来电声音';
  wrap.append(b,hint);return wrap;
}


const el=(t,cls,txt)=>{const x=document.createElement(t);if(cls)x.className=cls;if(txt)x.textContent=txt;return x;};
const page=el('section','upgrade-page');page.id='upgradePage';page.hidden=true;
const top=el('header','upgrade-top');const back=el('button','','← 返回首页');back.onclick=close;const heading=el('h1','','联系家人');top.append(back,heading);page.append(top);
const body=el('main','upgrade-body');page.append(body);document.body.append(page);
const status=el('p','upgrade-status');const api=async(path,method='GET',data)=>{const r=await fetch(path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error||'操作失败');return j;};
const btn=(txt,fn,cls='')=>{const b=el('button','upgrade-btn '+cls,txt);b.onclick=async()=>{try{await fn();}catch(e){status.textContent=e.message;}};return b;};
function open(title){heading.textContent=title;body.replaceChildren();status.textContent='';page.hidden=false;page.classList.add('visible');document.body.classList.add('upgrade-open');}
function close(){page.classList.remove('upgrade-in-call');if(currentCall)endCall();stopRadio();page.hidden=true;page.classList.remove('visible');document.body.classList.remove('upgrade-open');}
function note(text){status.textContent=text;}
function field(label,placeholder,type='text'){const l=el('label','upgrade-field');l.append(el('span','',label));const i=el('input');i.placeholder=placeholder;i.type=type;l.append(i);return [l,i];}
function familyCard(person){const c=el('article','upgrade-person');const avatar=el('img');avatar.alt=person.name+'的头像';avatar.src=person.avatar||'son.jpg';const name=el('h2','',person.name);c.append(avatar,name);c.append(btn('📞 联系'+person.name,()=>chooseCall(person.id,person.name),'upgrade-primary'));return c;}
async function contacts(){open('联系家人');body.append(el('p','upgrade-hint','点击家人的照片旁边按钮即可发起真实视频通话。'));const c=el('div','upgrade-grid');body.append(c);try{const data=await api('/api/upgrade/family');for(const p of data.contacts)c.append(familyCard(p));if(!data.contacts.length)body.append(el('p','upgrade-hint','还没有绑定家人。请先生成绑定码，让子女在手机网页中绑定。'));}catch(e){note(e.message);}const history=el('section','upgrade-history');history.append(el('h2','','历史通话'));body.append(history);loadHistory(history);const tools=el('div','upgrade-actions');tools.append(btn('🔑 生成子女绑定码',async()=>{const d=await api('/api/upgrade/pair','POST',{});note('请让子女在手机网页输入绑定码：'+d.code+'（10分钟有效）');}));tools.append(btn('📱 子女端入口',()=>{note('手机网页地址：'+location.origin+'/family.html。手机必须能访问此服务器；跨网络需安全部署 HTTPS。');}));body.append(tools,xljSoundEnableButton(),P28Ring.settingsButton(),status);}
async function loadHistory(container){try{const d=await api('/api/upgrade/call-history');if(!d.history.length){container.append(el('p','upgrade-hint','暂无历史通话'));return;}for(const c of d.history){const t=new Date(c.created*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});const dur=Math.floor(c.duration_seconds/60)+'分'+String(c.duration_seconds%60).padStart(2,'0')+'秒';const result=c.accepted_at?'通话 '+dur:c.status==='rejected'?'已拒接':'未接通';container.append(el('div','upgrade-history-item',(c.direction==='incoming'?'📥 ':'📤 ')+t+' · '+c.other_name+' · '+result));}}catch(e){container.append(el('p','upgrade-hint','记录加载失败：'+e.message));}}
let audio=null;
function stopRadio(){if(audio){audio.pause();audio.src='';audio=null;}}
async function radio(){open('实时收音机');body.append(el('p','upgrade-hint','只播放真实直播源；未验证的电台不会显示为“正在播放”。'));const cards=el('div','upgrade-grid');body.append(cards);try{const d=await api('/api/upgrade/radio');if(!d.stations.length)body.append(el('p','upgrade-hint','目前尚未配置经过验证、允许播放的电台直播源。可在 radio_stations.json 中添加合法的 HTTPS 直播地址。'));for(const s of d.stations){const card=el('article','upgrade-person');card.append(el('h2','',s.name));card.append(btn('▶ 播放直播',async()=>{stopRadio();audio=new Audio(s.url);audio.preload='none';audio.onerror=()=>note('电台直播源无法播放，请换一个频道');await audio.play();note('正在收听：'+s.name);}));cards.append(card);}}catch(e){note(e.message);}body.append(btn('⏸ 停止收听',()=>{stopRadio();note('已停止播放');}),status);}
async function qq(){open('QQ音乐');body.append(el('p','upgrade-hint','QQ音乐在 Windows 独立客户端打开，不会嵌入网页。'));body.append(btn('🎵 打开 Windows QQ音乐',async()=>{const d=await api('/api/upgrade/qqmusic','POST',{});note(d.message);},'upgrade-primary'),status);}
async function media(){open('我的媒体库');body.append(el('p','upgrade-hint','本地媒体库：现有秦腔音频可直接播放。后续可以扩展分类、批量导入和收藏。'));const files=[['秦腔选段','qinqiang.mp3'],['白蛇传','qinqiang_baishe.mp3'],['火焰驹','qinqiang_huoyanju.mp3'],['五典坡','qinqiang_wudianpo.mp3'],['周仁回府','qinqiang_zhouren.mp3']];const a=el('audio');a.controls=true;a.style.width='100%';body.append(a);for(const [name,file] of files)body.append(btn('▶ '+name,()=>{a.src='/audio/'+file;return a.play();}));}
let currentCallType='video',incomingShown=null;
let currentCall=null,pc=null,localStream=null,lastSignal=0,remoteVideo=null,callPoll=null,callStatus='',callClock=null,connectedAt=0;
let pendingIceCandidates=[];
 let polling=false, pollGeneration=0;
/* 小辣椒 TURN 配置：将下面的占位符替换为你在 coturn 中设置的 TURN 用户密码（不是阿里云登录/root 密码）。 */
const XLJ_ICE_SERVERS = [
  {urls:'stun:stun.l.google.com:19302'},
  {urls:'turn:60.205.195.155:3478?transport=udp', username:'xiaolajiao', credential:'4328da09f3898734fb03b887d8de54f1032711cdf49a5b04'},
  {urls:'turn:60.205.195.155:3478?transport=tcp', username:'xiaolajiao', credential:'4328da09f3898734fb03b887d8de54f1032711cdf49a5b04'}
];
 const rtc={iceServers:XLJ_ICE_SERVERS};
async function sendSignal(payload){return api('/api/upgrade/signal','POST',{id:currentCall,payload});}
async function setupRTC(){if(pc)return;localStream=await navigator.mediaDevices.getUserMedia({audio:true,video:currentCallType==='video'});pc=new RTCPeerConnection(rtc);for(const track of localStream.getTracks())pc.addTrack(track,localStream);pc.onicecandidate=e=>{if(e.candidate)sendSignal({candidate:e.candidate}).catch(console.error);};pc.ontrack=e=>{remoteVideo.srcObject=e.streams[0];};pc.onconnectionstatechange=()=>{if(!pc)return;console.info('[小辣椒RTC/老人] connectionState:',pc.connectionState,'ice:',pc.iceConnectionState);if(pc.connectionState==='connected'){P28Ring.stop();note('正在通话');startClock();}else if(pc.connectionState==='failed'){P28Ring.stop();note('音视频连接失败：请检查 ICE/TURN');}};pc.oniceconnectionstatechange=()=>console.info('[小辣椒RTC/老人] ICE:',pc?.iceConnectionState);const local=document.getElementById('upgradeLocalVideo');if(local)local.srcObject=localStream;}
async function offer(){await setupRTC();const d=await pc.createOffer();await pc.setLocalDescription(d);await sendSignal({description:pc.localDescription});}
async function handleSignal(p){if(p.description){await setupRTC();await pc.setRemoteDescription(p.description);for(const candidate of pendingIceCandidates.splice(0)){try{await pc.addIceCandidate(candidate);}catch(e){console.warn('ICE候选添加失败',e);}}if(p.description.type==='offer'){const a=await pc.createAnswer();await pc.setLocalDescription(a);await sendSignal({description:pc.localDescription});}}else if(p.candidate){if(!pc||!pc.remoteDescription){pendingIceCandidates.push(p.candidate);}else{try{await pc.addIceCandidate(p.candidate);}catch(e){console.warn('ICE候选添加失败',e);}}}}
async function pollCall(){if(!currentCall||polling)return;polling=true;const generation=pollGeneration;try{const d=await api('/api/upgrade/calls');const c=d.calls.find(x=>x.id===currentCall);if(!c||['ended','rejected'].includes(c.status)){await endCall(false);close();return;}if(c.status==='accepted'&&callStatus!=='accepted'){P28Ring.stop();callStatus='accepted';note('对方已接听，正在建立视频连接');if(c.caller_id===window.upgradeUserId)await offer();}const s=await api('/api/upgrade/signals?id='+encodeURIComponent(currentCall)+'&after='+lastSignal);for(const x of s.signals){if(generation!==pollGeneration||!currentCall)break;await handleSignal(x.payload);lastSignal=x.id;}}catch(e){console.error('[小辣椒RTC/老人] 信令处理失败',e);note('通话连接异常：'+e.message);}finally{polling=false;}}
function startClock(){if(callClock)return;connectedAt=Date.now();const label=document.getElementById('upgradeCallTimer');if(label)label.textContent='00:00';callClock=setInterval(()=>{const t=Math.floor((Date.now()-connectedAt)/1000);const x=document.getElementById('upgradeCallTimer');if(x)x.textContent=String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0');},1000);}
async function endCall(send=true){stopIncomingVoice();if(incomingWakeNeedsResume){incomingWakeNeedsResume=false;window.xljIncomingWakeBridge?.resume(true);}P28Ring.stop();clearInterval(callClock);callClock=null;const id=currentCall;currentCall=null;pollGeneration++;pendingIceCandidates=[];clearInterval(callPoll);callPoll=null;if(send&&id)try{await api('/api/upgrade/call-status','POST',{id,status:'ended'});}catch(e){}if(pc){pc.close();pc=null;}if(localStream){localStream.getTracks().forEach(x=>x.stop());localStream=null;}callStatus='';}
function callScreen(label){open((currentCallType==='voice'?'语音通话 · ':'视频通话 · ')+label);page.classList.add('upgrade-in-call');const timer=el('div','upgrade-call-timer','00:00');timer.id='upgradeCallTimer';const area=el('div','upgrade-videos');const localWrap=el('div','upgrade-video-box');const remoteWrap=el('div','upgrade-video-box');remoteVideo=el('video');remoteVideo.autoplay=true;remoteVideo.playsInline=true;const local=el('video');local.id='upgradeLocalVideo';local.autoplay=true;local.muted=true;local.playsInline=true;localWrap.append(local,el('span','upgrade-video-label','我'));remoteWrap.append(remoteVideo,el('span','upgrade-video-label',label));area.append(localWrap,remoteWrap);const actions=el('div','upgrade-call-actions');const volume=btn('🔊 声音调节',()=>{const v=remoteVideo.volume;remoteVideo.volume=v>=1?0.5:Math.min(1,v+0.25);note('播放音量 '+Math.round(remoteVideo.volume*100)+'%');});const mute=btn('🎙️ 静音',()=>{if(!localStream)return;const track=localStream.getAudioTracks()[0];if(track){track.enabled=!track.enabled;mute.textContent=track.enabled?'🎙️ 静音':'🔇 取消静音';}});actions.append(volume,btn('🔴 挂断电话',async()=>{await endCall();page.classList.remove('upgrade-in-call');contacts();},'upgrade-danger'),mute);if(currentCallType==='voice'){area.classList.add('upgrade-voice-call');localWrap.style.display='none';remoteWrap.style.display='none';area.append(el('div','upgrade-voice-avatar','📞 '+label));}body.append(timer,area,actions,status);}

function chooseCall(id,name){const mask=el('div','p28-elder-choice');const card=el('div','p28-elder-choice-card');card.append(el('h2','','联系 '+name),btn('📹 视频通话',()=>{mask.remove();startCall(id,name,'video');},'upgrade-primary'),btn('📞 语音通话',()=>{mask.remove();startCall(id,name,'voice');},'upgrade-primary'),btn('取消',()=>mask.remove()));mask.append(card);document.body.append(mask);}
async function startCall(id,name,type='video'){currentCallType=type;const me=await api('/api/auth/me');window.upgradeUserId=me.user.id;const c=await api('/api/upgrade/call','POST',{target:id,call_type:type});currentCall=c.id;pollGeneration++;pendingIceCandidates=[];lastSignal=0;callStatus='ringing';callScreen(name);P28Ring.start('outgoing');note('正在呼叫'+name+'，请等待对方接听…');callPoll=setInterval(pollCall,1600);}
// 来电语音接听：独立短时识别，仅在来电弹窗出现时工作。
let incomingVoice=null,incomingWakeNeedsResume=false;
function stopIncomingVoice(restoreWake=true){
  const v=incomingVoice;if(!v)return;
  incomingVoice=null;v.active=false;
  clearTimeout(v.timer);
  try{v.rec?.abort();}catch(_){}
  try{if(v.utterance)window.speechSynthesis?.cancel();}catch(_){}
  if(v.wakePaused)incomingWakeNeedsResume=true;
  if(restoreWake&&incomingWakeNeedsResume){incomingWakeNeedsResume=false;window.xljIncomingWakeBridge?.resume(true);}
}
function startIncomingVoice(mask,caller,acceptButton,rejectButton){
  stopIncomingVoice();
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  const state=el('p','upgrade-hint','小辣椒正在准备语音接听…');
  state.style.cssText='font-size:20px;font-weight:700;color:#23513a;margin:12px 0;';
  const card=mask.querySelector('.p28-elder-incoming-card');
  card?.insertBefore(state,acceptButton);
  const v={active:true,rec:null,timer:null,utterance:null,wakePaused:false,attempts:0};
  incomingVoice=v;
  v.wakePaused=!!window.xljIncomingWakeBridge?.pause();
  if(!SR){state.textContent='当前浏览器不支持语音接听，请点击下方按钮。';return;}
  const listen=()=>{
    if(!v.active||incomingVoice!==v||!mask.isConnected)return;
    let r;
    try{r=new SR();r.lang='zh-CN';r.continuous=false;r.interimResults=false;v.rec=r;}
    catch(e){state.textContent='语音识别不可用，请点击接听按钮。';return;}
    state.textContent='🎙 请说“接听”或“不接”';
    r.onresult=e=>{
      if(!v.active||incomingVoice!==v)return;
      const t=Array.from(e.results).map(x=>x[0]?.transcript||'').join('').replace(/[\s，。！？,.!?]/g,'');
      console.info('[小辣椒来电语音] 识别:',t);
      if(/(不接|别接|不要接|拒接|拒绝|挂掉|挂断|现在不方便|不方便接)/.test(t)){
        state.textContent='已听到“不接”，正在拒绝来电';stopIncomingVoice(false);rejectButton.click();return;
      }
      if(/(接听|接电话|接起来|接吧|接呀|接通|帮我接|好的接|好啊接|^(好|好的|可以|行|嗯|接)$)/.test(t)){
        state.textContent='已听到“接听”，正在接通';stopIncomingVoice(false);acceptButton.click();return;
      }
      state.textContent='没听清您的意思，请说“接听”或“不接”。';
    };
    r.onerror=e=>{if(!v.active)return;if(['not-allowed','service-not-allowed'].includes(e.error)){state.textContent='麦克风权限被拒绝，请点击接听按钮。';stopIncomingVoice();}};
    r.onend=()=>{
      if(!v.active||incomingVoice!==v)return;
      clearTimeout(v.timer);
      if(++v.attempts<3){v.timer=setTimeout(listen,650);}
      else{state.textContent='暂未听到回答，您仍可点击接听或拒绝。';stopIncomingVoice();P28Ring.start('incoming');}
    };
    try{r.start();}catch(e){state.textContent='无法启动语音识别，请点击下方按钮。';stopIncomingVoice();}
  };
  // 避免循环铃声干扰识别：暂停铃声，先语音询问，再开启麦克风。
  P28Ring.stop();
  const prompt='家人给您打'+(caller.call_type==='voice'?'语音':'视频')+'电话来了。您要接听吗？请说接听，或者不接。';
  if(!window.speechSynthesis){state.textContent='请说“接听”或“不接”。';listen();return;}
  try{
    const u=new SpeechSynthesisUtterance(prompt);v.utterance=u;u.lang='zh-CN';u.rate=.85;u.volume=1;
    u.onend=()=>{if(v.active)listen();};u.onerror=()=>{if(v.active)listen();};
    state.textContent='🔊 小辣椒正在询问是否接听…';
    window.speechSynthesis.cancel();window.speechSynthesis.speak(u);
    v.timer=setTimeout(()=>{if(v.active&&v.rec===null)listen();},6500);
  }catch(e){listen();}
}
async function checkIncoming(){if(currentCall)return;try{const me=await api('/api/auth/me');if(!me.user||me.user.role!=='elder')return;window.upgradeUserId=me.user.id;const d=await api('/api/upgrade/calls');const c=d.calls.find(x=>x.status==='ringing'&&x.caller_id!==me.user.id);if(incomingShown){if(!c||c.id!==incomingShown){incomingShown=null;stopIncomingVoice();P28Ring.stop();document.getElementById('p28ElderIncoming')?.remove();}return;}if(!c)return;incomingShown=c.id;P28Ring.stop();P28Ring.start('incoming');stopRadio();document.querySelectorAll('audio').forEach(a=>{try{a.pause();}catch(e){}});const mask=el('div','p28-elder-incoming');mask.id='p28ElderIncoming';const card=el('div','p28-elder-incoming-card');card.append(el('div','p28-elder-icon',c.call_type==='voice'?'📞':'📹'),el('h2','','家人正在呼叫您'),el('p','',c.call_type==='voice'?'语音来电':'视频来电'));const soundBtn=el('button','upgrade-btn','🔔 没有铃声？点此开启声音');soundBtn.type='button';soundBtn.onclick=async()=>{try{await P28Ring.enableIncoming();const s=P28Ring.diagnose();soundBtn.textContent=s.state==='playing'?'🔔 铃声正在播放':'⚠️ 音频未启动：'+s.state;console.info('[小辣椒铃声诊断]',s);}catch(e){soundBtn.textContent='⚠️ 声音启动失败';console.error('[小辣椒铃声]',e);}};card.append(soundBtn);const finish=(restore=true)=>{stopIncomingVoice(restore);P28Ring.stop();incomingShown=null;mask.remove();};card.append(btn('🔴 拒绝',async()=>{finish(true);await api('/api/upgrade/call-status','POST',{id:c.id,status:'rejected'});},'upgrade-danger'),btn('🟢 接听',async()=>{finish(false);currentCallType=c.call_type||'video';currentCall=c.id;pollGeneration++;pendingIceCandidates=[];lastSignal=0;callStatus='accepted';callScreen('家人来电');try{await setupRTC();await api('/api/upgrade/call-status','POST',{id:c.id,status:'accepted'});note('已接听，正在建立连接…');callPoll=setInterval(pollCall,1600);}catch(e){note('接听失败：'+e.message);await endCall();}},'upgrade-primary'));mask.append(card);document.body.append(mask);const answer=Array.from(card.querySelectorAll('button')).find(b=>b.textContent.includes('🟢 接听'));const reject=Array.from(card.querySelectorAll('button')).find(b=>b.textContent.includes('🔴 拒绝'));if(answer&&reject)startIncomingVoice(mask,c,answer,reject);}catch(e){console.warn('来电检查',e);}}
setInterval(checkIncoming,2500);document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkIncoming();});
// Capture existing buttons so old popups do not open beneath new pages.
document.addEventListener('click',e=>{const b=e.target.closest('[data-act]');if(!b)return;const a=b.dataset.act;if(a==='family'||a==='contacts'||a==='media'){e.preventDefault();e.stopImmediatePropagation();if(a==='family'||a==='contacts'){document.getElementById('contactsOverlay')?.classList.remove('show','p257-page');contacts();}else entertainment();}},true);
function entertainment(){open('影音娱乐');const g=el('div','upgrade-grid');g.append(btn('📚 我的媒体库',media),btn('🎵 QQ音乐',qq),btn('📻 实时收音机',radio));body.append(g);}
window.xljUpgrade={contacts,radio,qq,media,entertainment,close,startCall};
// 语音快捷指令：只处理明确的操作请求，不拦截普通聊天。
// 注意：本入口由首页语音识别模块调用；它本身不负责持续监听或唤醒词检测。
window.xljUpgradeVoice=async(text)=>{
  let t=String(text||'').replace(/[\s，。！？、,.!?：:]/g,'');
  t=t.replace(/^(?:小辣椒){1,3}/,'').replace(/^(?:请|你|能不能|可以|麻烦你|帮我|给我)+/,'');
  if(/^(打开|进入|启动)QQ音乐/.test(t)){await qq();return true;}
  if(/^(打开|进入)(收音机|电台)/.test(t)){await radio();return true;}
  const isCall=/(?:打|拨|接通|发起|联系|呼叫|视频|通话)/.test(t)
    && /(?:电话|视频|通话|联系|呼叫)/.test(t)
    && /(?:儿子|女儿|家人|孩子|老伴|孙子|孙女|联系人)/.test(t);
  if(!isCall)return false;
  if(currentCall){note('当前正在通话，请先结束通话。');return true;}
  const who=(t.match(/儿子|女儿|老伴|孙子|孙女/)||[])[0]||'';
  // 不确定对象时展示已绑定联系人；明确对象时也先确认，避免误拨。
  await contacts();
  try{
    const data=await api('/api/upgrade/family');
    const list=Array.isArray(data.contacts)?data.contacts:[];
    const matched=who?list.filter(p=>String(p.name||'').includes(who)):[];
    if(who&&matched.length===1){
      note('已找到'+matched[0].name+'，请选择视频通话或语音通话。');
      chooseCall(matched[0].id,matched[0].name);
    }else if(who&&matched.length===0){
      note('还没有找到“'+who+'”的绑定联系人，请先绑定或从列表中选择。');
    }else{
      note('您想联系哪位家人？请点击对应家人的“联系”按钮。');
    }
  }catch(e){note('联系人读取失败：'+e.message);}
  return true;
};
})();

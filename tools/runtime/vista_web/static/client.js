const $ = id => document.getElementById(id);
const screen = $('screen'), keys = new Set(), taps = new Set();
const allowed = new Set(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowLeft','ArrowDown','ArrowRight','ShiftLeft','Space','KeyE','KeyG','KeyQ','KeyF','KeyC','KeyB','Tab','Escape',...Array.from({length:6},(_,i)=>`Digit${i+1}`)]);
let pc, channel, active=false, wanted=false, pending=null, lastClaim=0, seq=0, dx=0, dy=0, drag=false, lastX=0, lastY=0, statsTimer, inputTimer, heartbeatTimer, noticeTimer;
let received = new MediaStream(), startX=0, startY=0;
const send = packet => { if(channel?.readyState==='open') channel.send(JSON.stringify(packet)); };
function notice(text){$('notice').textContent=text;$('notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').hidden=true,6500);}
function controlled(value){active=value;taps.clear();dx=dy=0;$('control').classList.toggle('active',value);$('control').textContent=value?'Release control':'Take control';if(value&&pending){const key=pending;pending=null;tap(key);}}
// Keys, clicks and returning to the page re-claim; the server never lets this override another controller.
function claim(){const now=performance.now();if(active||channel?.readyState!=='open'||now-lastClaim<800)return;lastClaim=now;wanted=true;send({type:'claim'});}
function packet(){if(!active)return;send({type:'input',seq:++seq,keys:[...new Set([...keys,...taps])],dx:Math.max(-100,Math.min(100,dx)),dy:Math.max(-100,Math.min(100,dy))});dx=dy=0;}
function release(){keys.clear();taps.clear();if(active){packet();send({type:'release'});}controlled(false);drag=false;if(document.pointerLockElement)document.exitPointerLock();}
function idle(){keys.clear();taps.clear();drag=false;packet();if(document.pointerLockElement)document.exitPointerLock();}
async function sound(){screen.muted=false;try{await screen.play();$('sound').textContent='Mute sound';}catch{screen.muted=true;screen.play().catch(()=>{});$('sound').textContent='Sound on';notice('Click Sound on to hear the environment.');}}
function tap(key){if(!active){pending=key;claim();return;}taps.add(key);packet();setTimeout(()=>{taps.delete(key);packet();},140);}
async function leave(){wanted=false;pending=null;release();clearInterval(inputTimer);clearInterval(statsTimer);clearInterval(heartbeatTimer);channel?.close();pc?.close();pc=null;channel=null;received=new MediaStream();screen.srcObject=null;$('welcome').hidden=false;$('toolbar').hidden=$('hints').hidden=$('touch').hidden=true;$('status').textContent='Disconnected';$('connect').disabled=false;}
async function connect(){
  $('connect').disabled=true;$('status').textContent='Connecting…';
  try{
    pc=new RTCPeerConnection({iceServers:[]});
    channel=pc.createDataChannel('vista-input',{ordered:true});
    channel.onopen=()=>{lastClaim=0;claim();inputTimer=setInterval(packet,50);heartbeatTimer=setInterval(()=>send({type:'ping',at:Date.now()}),1000);};
    channel.onmessage=event=>{const data=JSON.parse(event.data);if(data.type==='control'){controlled(data.active);if(!data.active&&wanted&&!document.hidden)setTimeout(()=>{lastClaim=0;claim();},300);}if(data.type==='error'){pending=null;controlled(false);notice(data.message);}};
    channel.onclose=()=>controlled(false);
    pc.ontrack=event=>{received.addTrack(event.track);screen.srcObject=received;screen.play().catch(()=>{$('sound').textContent='Sound on';});};
    pc.onconnectionstatechange=()=>{if(!pc)return;const state=pc.connectionState;$('status').textContent=state==='connected'?'Live · Original environment':state;if(state==='disconnected')idle();if(['failed','closed'].includes(state))release();if(state==='connected'&&wanted&&!document.hidden)claim();if(state==='failed')notice('Connection interrupted. Leave and reconnect.');};
    pc.addTransceiver('video',{direction:'recvonly'});pc.addTransceiver('audio',{direction:'recvonly'});
    await pc.setLocalDescription(await pc.createOffer());
    if(pc.iceGatheringState!=='complete')await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(new Error('Connection setup timed out.')),6000);pc.addEventListener('icegatheringstatechange',()=>{if(pc.iceGatheringState==='complete'){clearTimeout(timeout);resolve();}});});
    const response=await fetch('/offer',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sdp:pc.localDescription.sdp,type:pc.localDescription.type})});
    if(!response.ok)throw new Error(response.status===503?'The environment is busy. Please try again.':'Could not connect to the native environment.');
    await pc.setRemoteDescription(await response.json());
    $('welcome').hidden=true;$('toolbar').hidden=$('hints').hidden=false;$('touch').hidden=!matchMedia('(pointer:coarse)').matches;
    await sound();statsTimer=setInterval(async()=>{if(!pc)return;const stats=await pc.getStats();for(const row of stats.values())if(row.type==='inbound-rtp'&&row.kind==='video')$('quality').textContent=`${row.frameWidth||1920} × ${row.frameHeight||1080} · ${Math.round(row.framesPerSecond||0)} fps`;},2000);
  }catch(error){await leave();notice(error.message);}
}
$('connect').onclick=connect;$('disconnect').onclick=leave;
$('control').onclick=()=>{if(active){wanted=false;pending=null;release();}else{lastClaim=0;claim();}};
$('sound').onclick=()=>{if(screen.muted||screen.paused)sound();else{screen.muted=true;$('sound').textContent='Sound on';}};
$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else $('world').requestFullscreen?.().catch(()=>notice('Full screen is unavailable in this browser.'));};
document.querySelectorAll('[data-tap]').forEach(button=>button.onclick=()=>tap(button.dataset.tap));
window.addEventListener('keydown',event=>{if(!channel||!allowed.has(event.code)||event.metaKey||event.ctrlKey||event.altKey||event.target.tagName==='SELECT')return;event.preventDefault();keys.add(event.code);if(active)packet();else claim();});
window.addEventListener('keyup',event=>{if(!allowed.has(event.code))return;keys.delete(event.code);packet();});
screen.addEventListener('pointerdown',event=>{if(!active)claim();drag=true;lastX=startX=event.clientX;lastY=startY=event.clientY;screen.setPointerCapture(event.pointerId);});
screen.addEventListener('pointermove',event=>{if(!active)return;if(document.pointerLockElement===screen){dx+=event.movementX;dy+=event.movementY;}else if(drag){dx+=(event.clientX-lastX)*1.1;dy+=(event.clientY-lastY)*1.1;lastX=event.clientX;lastY=event.clientY;}});
screen.addEventListener('pointerup',event=>{if(active&&drag&&Math.hypot(event.clientX-startX,event.clientY-startY)<5&&!document.pointerLockElement){const box=screen.getBoundingClientRect(),scale=Math.min(box.width/screen.videoWidth,box.height/screen.videoHeight),w=screen.videoWidth*scale,h=screen.videoHeight*scale,x=(event.clientX-box.left-(box.width-w)/2)/w,y=(event.clientY-box.top-(box.height-h)/2)/h;if(x>=0&&x<=1&&y>=0&&y<=1)send({type:'click',x,y});}drag=false;});screen.addEventListener('pointercancel',()=>{drag=false;});
screen.addEventListener('dblclick',()=>{if(active)try{screen.requestPointerLock?.()?.catch(()=>notice('Drag to look around.'));}catch{notice('Drag to look around.');}});
screen.addEventListener('contextmenu',event=>event.preventDefault());
document.querySelectorAll('[data-hold]').forEach(button=>{button.onpointerdown=event=>{event.preventDefault();if(!active)claim();button.setPointerCapture(event.pointerId);keys.add(button.dataset.hold);packet();};const up=()=>{keys.delete(button.dataset.hold);packet();};button.onpointerup=up;button.onpointercancel=up;});
// Losing focus only lifts held keys; a hidden tab gives control back so it cannot block the visible one.
window.addEventListener('blur',idle);window.addEventListener('focus',()=>{if(wanted)claim();});window.addEventListener('pagehide',()=>{release();pc?.close();});document.addEventListener('visibilitychange',()=>{if(document.hidden)release();else if(wanted)claim();});
// Read-only diagnostics for local transport verification. No native state injection.
window.vistaStream={stats:async()=>pc?[...(await pc.getStats()).values()]:[],get controlled(){return active;},get connected(){return pc?.connectionState;}};

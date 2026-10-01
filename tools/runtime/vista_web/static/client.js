const $ = id => document.getElementById(id);
const screen = $('screen'), keys = new Set(), taps = new Set();
const allowed = new Set(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowLeft','ArrowDown','ArrowRight','ShiftLeft','Space','KeyE','KeyG','KeyQ','KeyF','KeyC','KeyB','Tab','Escape',...Array.from({length:6},(_,i)=>`Digit${i+1}`)]);
let pc, channel, active=false, seq=0, dx=0, dy=0, drag=false, lastX=0, lastY=0, statsTimer, inputTimer, noticeTimer;
let received = new MediaStream(), startX=0, startY=0;
const send = packet => { if(channel?.readyState==='open') channel.send(JSON.stringify(packet)); };
function notice(text){$('notice').textContent=text;$('notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('notice').hidden=true,6500);}
function controlled(value){active=value;keys.clear();taps.clear();dx=dy=0;$('control').classList.toggle('active',value);$('control').textContent=value?'Release control':'Take control';}
function packet(){if(!active)return;send({type:'input',seq:++seq,keys:[...new Set([...keys,...taps])],dx:Math.max(-100,Math.min(100,dx)),dy:Math.max(-100,Math.min(100,dy))});dx=dy=0;}
function release(){if(active){keys.clear();taps.clear();packet();send({type:'release'});}controlled(false);drag=false;if(document.pointerLockElement)document.exitPointerLock();}
async function sound(){screen.muted=false;try{await screen.play();$('sound').textContent='Mute sound';}catch{notice('Click Sound on to hear the environment.');}}
function tap(key){if(!active){notice('Click Take control first.');return;}taps.add(key);packet();setTimeout(()=>{taps.delete(key);packet();},140);}
async function leave(){release();clearInterval(inputTimer);clearInterval(statsTimer);channel?.close();pc?.close();pc=null;channel=null;received=new MediaStream();screen.srcObject=null;$('welcome').hidden=false;$('toolbar').hidden=$('hints').hidden=$('touch').hidden=true;$('status').textContent='Disconnected';$('connect').disabled=false;}
async function connect(){
  $('connect').disabled=true;$('status').textContent='Connecting…';
  try{
    pc=new RTCPeerConnection({iceServers:[]});
    channel=pc.createDataChannel('vista-input',{ordered:true});
    channel.onopen=()=>{send({type:'claim'});inputTimer=setInterval(packet,50);};
    channel.onmessage=event=>{const data=JSON.parse(event.data);if(data.type==='control')controlled(data.active);if(data.type==='error'){controlled(false);notice(data.message);}};
    channel.onclose=()=>controlled(false);
    pc.ontrack=event=>{received.addTrack(event.track);screen.srcObject=received;screen.play().catch(()=>{$('sound').textContent='Sound on';});};
    pc.onconnectionstatechange=()=>{if(!pc)return;const state=pc.connectionState;$('status').textContent=state==='connected'?'Live · Original environment':state;if(['failed','disconnected','closed'].includes(state))release();if(state==='failed')notice('Connection interrupted. Leave and reconnect.');};
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
$('control').onclick=()=>{if(active)release();else send({type:'claim'});};
$('sound').onclick=()=>{if(screen.muted||screen.paused)sound();else{screen.muted=true;$('sound').textContent='Sound on';}};
$('fullscreen').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else $('world').requestFullscreen?.().catch(()=>notice('Full screen is unavailable in this browser.'));};
document.querySelectorAll('[data-tap]').forEach(button=>button.onclick=()=>tap(button.dataset.tap));
window.addEventListener('keydown',event=>{if(!active||!allowed.has(event.code)||event.metaKey||event.ctrlKey||event.altKey||event.target.tagName==='SELECT')return;event.preventDefault();keys.add(event.code);packet();});
window.addEventListener('keyup',event=>{if(!allowed.has(event.code))return;keys.delete(event.code);packet();});
screen.addEventListener('pointerdown',event=>{if(!active){notice('Click Take control to move.');return;}drag=true;lastX=startX=event.clientX;lastY=startY=event.clientY;screen.setPointerCapture(event.pointerId);});
screen.addEventListener('pointermove',event=>{if(!active)return;if(document.pointerLockElement===screen){dx+=event.movementX;dy+=event.movementY;}else if(drag){dx+=(event.clientX-lastX)*1.1;dy+=(event.clientY-lastY)*1.1;lastX=event.clientX;lastY=event.clientY;}});
screen.addEventListener('pointerup',event=>{if(active&&drag&&Math.hypot(event.clientX-startX,event.clientY-startY)<5&&!document.pointerLockElement){const box=screen.getBoundingClientRect(),scale=Math.min(box.width/screen.videoWidth,box.height/screen.videoHeight),w=screen.videoWidth*scale,h=screen.videoHeight*scale,x=(event.clientX-box.left-(box.width-w)/2)/w,y=(event.clientY-box.top-(box.height-h)/2)/h;if(x>=0&&x<=1&&y>=0&&y<=1)send({type:'click',x,y});}drag=false;});screen.addEventListener('pointercancel',()=>{drag=false;});
screen.addEventListener('dblclick',()=>{if(active)try{screen.requestPointerLock?.()?.catch(()=>notice('Drag to look around.'));}catch{notice('Drag to look around.');}});
screen.addEventListener('contextmenu',event=>event.preventDefault());
document.querySelectorAll('[data-hold]').forEach(button=>{button.onpointerdown=event=>{if(!active)return;event.preventDefault();button.setPointerCapture(event.pointerId);keys.add(button.dataset.hold);packet();};const up=()=>{keys.delete(button.dataset.hold);packet();};button.onpointerup=up;button.onpointercancel=up;});
window.addEventListener('blur',release);window.addEventListener('pagehide',()=>{release();pc?.close();});document.addEventListener('visibilitychange',()=>{if(document.hidden)release();});
// Read-only diagnostics for local transport verification. No native state injection.
window.vistaStream={stats:async()=>pc?[...(await pc.getStats()).values()]:[],get controlled(){return active;},get connected(){return pc?.connectionState;}};

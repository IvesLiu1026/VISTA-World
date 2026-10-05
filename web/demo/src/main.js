import * as T from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {ROOMS,WorldState,parseScenario,slideMove,findPath,blocked} from './simulation.js';
import {buildRoom} from './rooms.js';
import './style.css';

const $=id=>document.getElementById(id),state=new WorldState();
let previousTime=performance.now();
let entered=false,room,third=true,yaw=0,pitch=.26,pressed=new Set(),drag=null,stick={x:0,z:0},messageUntil=0;
let agentPath=[],agentGoal=null,planClock=0,action=null,phoneBlend=0;
const scene=new T.Scene();scene.background=new T.Color(0xb7c4b4);scene.fog=new T.Fog(0xb7c4b4,17,45);
const camera=new T.PerspectiveCamera(56,innerWidth/innerHeight,.06,70);
const renderer=new T.WebGLRenderer({antialias:true,powerPreference:'high-performance'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.4));renderer.setSize(innerWidth,innerHeight);renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFShadowMap;
renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.15;renderer.outputColorSpace=T.SRGBColorSpace;
$('world').append(renderer.domElement);
scene.add(new T.HemisphereLight(0xe5efff,0x887052,2.4));
const sun=new T.DirectionalLight(0xffebc8,3.0);sun.position.set(-5,9,7);sun.castShadow=true;sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-8;sun.shadow.camera.right=8;sun.shadow.camera.top=8;sun.shadow.camera.bottom=-8;sun.shadow.normalBias=.025;sun.shadow.bias=-.00015;scene.add(sun);
const ground=new T.Mesh(new T.PlaneGeometry(100,100),new T.MeshStandardMaterial({color:0x7e9170,roughness:1}));ground.rotation.x=-Math.PI/2;ground.position.y=-.12;ground.receiveShadow=true;scene.add(ground);
for(let i=0;i<30;i++){
  const a=i*2.399,r=10+(i%7)*1.2,tree=new T.Group();tree.position.set(Math.cos(a)*r,0,Math.sin(a)*r);
  const trunk=new T.Mesh(new T.CylinderGeometry(.06,.12,2,8),new T.MeshStandardMaterial({color:0x6c604c}));trunk.position.y=.9;tree.add(trunk);
  const foliage=new T.Mesh(new T.IcosahedronGeometry(1.15+(i%3)*.2,1),new T.MeshStandardMaterial({color:i%2?0x78916a:0x6a8058,roughness:1}));foliage.position.y=2.3;foliage.scale.y=1.2;foliage.castShadow=true;tree.add(foliage);scene.add(tree);
}
const player={position:new T.Vector3(0,0,2.3),velocity:new T.Vector3(),heading:Math.PI};
const companion={position:new T.Vector3(-1.55,0,1.8),velocity:new T.Vector3(),heading:Math.PI};
const loader=new GLTFLoader();
function message(text){$('subtitle').textContent=text;messageUntil=state.time+5;}
function angleDelta(a,b){return Math.atan2(Math.sin(b-a),Math.cos(b-a));}
function orient(actor,target,dt){actor.heading+=T.MathUtils.clamp(angleDelta(actor.heading,target),-2.5*dt,2.5*dt);}

class Avatar{
  constructor(gltf,height){
    this.root=new T.Group();this.model=gltf.scene;this.root.add(this.model);scene.add(this.root);
    this.model.updateMatrixWorld(true);const bounds=new T.Box3().setFromObject(this.model),size=bounds.getSize(new T.Vector3());
    const scale=height/size.y;this.model.scale.setScalar(scale);this.model.position.y=-bounds.min.y*scale;
    this.mixer=new T.AnimationMixer(this.model);this.actions={};this.weight=0;this.bones={};
    for(const clip of gltf.animations){const action=this.mixer.clipAction(clip);action.play();action.setEffectiveWeight(clip.name==='Idle'?1:0);this.actions[clip.name]=action;}
    this.model.traverse(o=>{if(o.isMesh){o.castShadow=!/fiber|eye|teeth|brow|lash|thumb|index|middle/i.test(o.name);o.receiveShadow=false;o.frustumCulled=false;}if(o.isBone)this.bones[o.name]=o;});
    this.strideSpeed=1.43164/1.1*scale;
  }
  update(actor,dt){
    this.root.position.copy(actor.position);this.root.rotation.y=actor.heading;
    const speed=actor.velocity.length();this.weight=T.MathUtils.damp(this.weight,Math.min(1,speed/.85),9,dt);
    this.actions.Idle?.setEffectiveWeight(1-this.weight);this.actions.Walk?.setEffectiveWeight(this.weight);
    this.actions.Walk?.setEffectiveTimeScale(speed/this.strideSpeed);this.mixer.update(dt);this.root.updateMatrixWorld(true);
  }
  reach(side,goal,alpha){
    const upper=this.bones['upperarm_'+side],lower=this.bones['lowerarm_'+side],hand=this.bones['hand_'+side];if(!upper||!lower||!hand||alpha<.001)return;
    this.root.updateMatrixWorld(true);
    const a=upper.getWorldPosition(new T.Vector3()),b=lower.getWorldPosition(new T.Vector3()),c=hand.getWorldPosition(new T.Vector3());
    const target=c.clone().lerp(goal,alpha),l1=a.distanceTo(b),l2=b.distanceTo(c),n=target.clone().sub(a).normalize(),d=T.MathUtils.clamp(a.distanceTo(target),Math.abs(l1-l2)+.002,l1+l2-.005);
    const pole=b.clone().sub(a);pole.addScaledVector(n,-pole.dot(n));if(pole.length()<.01)pole.set(side==='r'?1:-1,-.3,.2);pole.normalize();
    const along=(l1*l1-l2*l2+d*d)/(2*d),joint=a.clone().addScaledVector(n,along).addScaledVector(pole,Math.sqrt(Math.max(0,l1*l1-along*along)));
    const rotate=(bone,from,to)=>{
      const q=new T.Quaternion().setFromUnitVectors(from.normalize(),to.normalize()).multiply(bone.getWorldQuaternion(new T.Quaternion()));
      bone.quaternion.copy(bone.parent.getWorldQuaternion(new T.Quaternion()).invert().multiply(q));bone.updateMatrixWorld(true);
    };
    rotate(upper,b.clone().sub(a),joint.clone().sub(a));
    const knee=lower.getWorldPosition(new T.Vector3()),wrist=hand.getWorldPosition(new T.Vector3());
    rotate(lower,wrist.sub(knee),a.clone().addScaledVector(n,d).sub(knee));this.root.updateMatrixWorld(true);
  }
}
let human,robot;
const heldPhone=new T.Mesh(new T.BoxGeometry(.073,.145,.013),new T.MeshStandardMaterial({color:0x243735,roughness:.3,metalness:.4}));scene.add(heldPhone);heldPhone.visible=false;
function setRoom(id,keepState=false){
  action=null;agentPath=[];agentGoal=null;planClock=0;phoneBlend=0;
  room?.dispose();if(!keepState)state.reset(id);room=buildRoom(scene,id);
  player.position.set(0,0,2.35);companion.position.set(-1.55,0,1.8);player.velocity.set(0,0,0);companion.velocity.set(0,0,0);player.heading=companion.heading=Math.PI;
  yaw=0;pitch=.27;$('room').value=id;$('scene-index').textContent=String(ROOMS.findIndex(r=>r.id===id)+1).padStart(2,'0')+' / 06';
  const spec=ROOMS.find(r=>r.id===id);$('scene-name').textContent=spec.name;$('scene-description').textContent=spec.description;
  $('subtitle').textContent='';$('assist-toggle').textContent=state.assistance?'Assistance on':'Assistance off';$('assist-toggle').setAttribute('aria-pressed',String(state.assistance));
  updateCamera(1,true);
}
for(const r of ROOMS){const option=document.createElement('option');option.value=r.id;option.textContent=r.name;$('room').append(option);}
$('room').addEventListener('change',()=>setRoom($('room').value));
$('reset').onclick=()=>setRoom(state.room);
function switchView(){third=!third;$('view').textContent=third?'Third person':'First person';if(human)human.root.visible=third;updateCamera(1,true);}
$('view').onclick=switchView;$('help').onclick=()=>$('information').showModal();
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>$(b.dataset.close).close();
$('scenario-open').onclick=()=>$('scenario').showModal();
for(const b of document.querySelectorAll('[data-prompt]'))b.onclick=()=>{$('prompt').value=b.dataset.prompt;$('scenario-error').textContent='';};
$('scenario-form').onsubmit=e=>{
  e.preventDefault();const spec=parseScenario($('prompt').value);
  if(!spec.supported){$('scenario-error').textContent=spec.reason??'Please enter a shorter supported situation.';return;}
  state.stage(spec);setRoom(spec.room,true);$('scenario').close();
  message(spec.phone?'You: “Hi, yes, I have a minute to talk.”':'Assistant: “I’ll stay nearby.”');
};
$('assist-toggle').onclick=()=>{
  state.assistance=!state.assistance;action=null;agentPath=[];agentGoal=null;
  $('assist-toggle').textContent=state.assistance?'Assistance on':'Assistance off';$('assist-toggle').setAttribute('aria-pressed',String(state.assistance));
};
const modal=()=>!!document.querySelector('dialog[open]');
window.addEventListener('keydown',e=>{if(!entered||modal())return;if(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowLeft','ArrowDown','ArrowRight','Space'].includes(e.code))e.preventDefault();pressed.add(e.code);if(e.code==='KeyE'&&!e.repeat)interact();if(e.code==='KeyV'&&!e.repeat)switchView();});
window.addEventListener('keyup',e=>pressed.delete(e.code));window.addEventListener('blur',()=>{pressed.clear();stick={x:0,z:0};});
renderer.domElement.addEventListener('pointerdown',e=>{if(!entered||modal())return;drag={id:e.pointerId,x:e.clientX,y:e.clientY};renderer.domElement.setPointerCapture(e.pointerId);});
renderer.domElement.addEventListener('pointermove',e=>{if(drag?.id!==e.pointerId)return;yaw-=(e.clientX-drag.x)*.005;pitch=T.MathUtils.clamp(pitch+(e.clientY-drag.y)*.004,-.35,.8);drag.x=e.clientX;drag.y=e.clientY;});
renderer.domElement.addEventListener('pointerup',()=>drag=null);renderer.domElement.addEventListener('pointercancel',()=>drag=null);
const joy=$('joystick'),nub=joy.firstElementChild;
function joystick(e){const b=joy.getBoundingClientRect(),x=T.MathUtils.clamp((e.clientX-b.x-b.width/2)/32,-1,1),z=T.MathUtils.clamp((e.clientY-b.y-b.height/2)/32,-1,1);stick={x,z};nub.style.transform=`translate(${x*23}px,${z*23}px)`;}
joy.onpointerdown=e=>{e.preventDefault();joy.setPointerCapture(e.pointerId);joystick(e);};joy.onpointermove=e=>{if(joy.hasPointerCapture(e.pointerId))joystick(e);};joy.onpointerup=joy.onpointercancel=()=>{stick={x:0,z:0};nub.style.transform='';};
function nearest(){
  if(state.phone)return {id:'phone',label:'End the call'};
  return Object.entries(room.targets).map(([id,t])=>({id,d:Math.hypot(player.position.x-t.position.x,player.position.z-t.position.z),...t})).filter(t=>t.d<1.55).sort((a,b)=>a.d-b.d)[0];
}
function interact(){const target=nearest();if(!target)return;
  if(target.id==='phone'){state.phone=!state.phone;message(state.phone?'You: “Hey, how’s your day going?”':'You: “Talk soon. Bye.”');}
  if(target.id==='stove'){state.stove=!state.stove;message(state.stove?'You turned on the stove.':'You turned off the stove.');}
  if(target.id==='tap'){state.tap=!state.tap;message(state.tap?'You started filling the bath.':'You stopped the water.');}
  action=null;agentGoal=null;agentPath=[];
}
$('interact').onclick=interact;
function updatePlayer(dt){
  let x=stick.x+Number(pressed.has('KeyD')||pressed.has('ArrowRight'))-Number(pressed.has('KeyA')||pressed.has('ArrowLeft'));
  let z=stick.z+Number(pressed.has('KeyS')||pressed.has('ArrowDown'))-Number(pressed.has('KeyW')||pressed.has('ArrowUp'));
  if(modal())x=z=0;
  const input=new T.Vector3(x,0,z);if(input.length()>1)input.normalize();input.applyAxisAngle(T.Object3D.DEFAULT_UP,yaw);
  const desired=input.multiplyScalar(1.7),response=1-Math.exp(-dt*7);player.velocity.lerp(desired,response);
  const before=player.position.clone();slideMove(player.position,player.velocity.x*dt,player.velocity.z*dt,room.colliders);
  const separation=player.position.clone().sub(companion.position);separation.y=0;if(separation.length()<.58&&separation.length()>.001){const corrected=companion.position.clone().add(separation.normalize().multiplyScalar(.58));if(!blocked(corrected.x,corrected.z,room.colliders)){player.position.x=corrected.x;player.position.z=corrected.z;}else player.position.copy(before);}
  player.velocity.copy(player.position).sub(before).divideScalar(dt);
  if(player.velocity.length()>.03)orient(player,Math.atan2(player.velocity.x,player.velocity.z),dt);
  else if(!third&&Math.abs(angleDelta(player.heading,yaw+Math.PI))>1.25)orient(player,yaw+Math.PI,dt);
}
function updateAgent(dt){
  planClock-=dt;const intent=state.intention();
  if(action&&(!state.assistance||(action.target==='stove'&&!state.stove)||(action.target==='tap'&&!state.tap))){action=null;agentPath=[];agentGoal=null;}
  if(intent&&!action){action={...intent,phase:'approach',clock:0,version:state.version};agentGoal=null;message('Assistant: “'+intent.line+'”');}
  let goal=null;
  if(action)goal=room.targets[action.target]?.approach;
  else if(state.assistance&&companion.position.distanceTo(player.position)>1.8){
    const away=companion.position.clone().sub(player.position).setY(0).normalize().multiplyScalar(1.4);goal={x:player.position.x+away.x,z:player.position.z+away.z};
  }
  if(goal&&planClock<=0){agentPath=findPath(companion.position,goal,room.colliders);agentGoal=goal;planClock=.55;}
  if(!goal){agentPath=[];agentGoal=null;}
  while(agentPath.length&&Math.hypot(agentPath[0].x-companion.position.x,agentPath[0].z-companion.position.z)<.16)agentPath.shift();
  const before=companion.position.clone(),desired=new T.Vector3();
  if(agentPath.length){const p=agentPath[0];desired.set(p.x-companion.position.x,0,p.z-companion.position.z);const distance=agentGoal?Math.hypot(agentGoal.x-companion.position.x,agentGoal.z-companion.position.z):2;desired.normalize().multiplyScalar(Math.min(1.45,Math.sqrt(2*1.8*Math.max(.01,distance-.12))));orient(companion,Math.atan2(desired.x,desired.z),dt);}
  companion.velocity.lerp(desired,1-Math.exp(-dt*7));slideMove(companion.position,companion.velocity.x*dt,companion.velocity.z*dt,room.colliders,.3);
  if(companion.position.distanceTo(player.position)<.64)companion.position.copy(before);
  companion.velocity.copy(companion.position).sub(before).divideScalar(dt);
  if(action&&goal&&Math.hypot(goal.x-companion.position.x,goal.z-companion.position.z)<.42){
    action.phase='reach';action.clock+=dt;const target=room.targets[action.target].position;orient(companion,Math.atan2(target.x-companion.position.x,target.z-companion.position.z),dt);
    if(action.clock>1.4&&action.version===state.version){state.complete(action.target);message(action.target==='tap'?'Assistant: “The water is off. You can finish your call.”':'Assistant: “The stove is off. You’re all set.”');action=null;agentPath=[];agentGoal=null;}
  }
  $('agent-status').textContent=action?(action.phase==='reach'?'Operating the control':'Moving to help'):state.assistance?'Assistant nearby':'Assistant waiting';
}
const ray=new T.Raycaster(),cameraTarget=new T.Vector3();
function updateCamera(dt,instant=false){
  const target=player.position.clone().add(new T.Vector3(0,third?1.18:1.53,0));
  let desired;
  if(third){
    const direction=new T.Vector3(Math.sin(yaw)*Math.cos(pitch),Math.sin(pitch),Math.cos(yaw)*Math.cos(pitch));
    ray.set(target,direction);ray.far=3.45;const hits=room?ray.intersectObjects(room.walls,false):[];
    const distance=hits.length?Math.max(.35,hits[0].distance-.18):3.45;desired=target.clone().addScaledVector(direction,distance);cameraTarget.copy(target);
  }else{desired=target;cameraTarget.copy(target).add(new T.Vector3(-Math.sin(yaw)*Math.cos(pitch),-Math.sin(pitch),-Math.cos(yaw)*Math.cos(pitch)));}
  camera.position.lerp(desired,instant?1:1-Math.exp(-dt*15));camera.lookAt(cameraTarget);
}
function updateVisuals(dt){
  if(human){human.root.visible=third;human.update(player,dt);robot.update(companion,dt);
    phoneBlend=T.MathUtils.damp(phoneBlend,state.phone?1:0,6,dt);
    if(phoneBlend>.005){const head=human.bones.head.getWorldPosition(new T.Vector3()),offset=new T.Vector3(.13,-.05,.005).applyAxisAngle(T.Object3D.DEFAULT_UP,player.heading);human.reach('r',head.add(offset),phoneBlend);const hand=human.bones.hand_r;heldPhone.position.copy(hand.getWorldPosition(new T.Vector3()));heldPhone.quaternion.copy(hand.getWorldQuaternion(new T.Quaternion()));}
    heldPhone.visible=state.phone&&third;
    if(action?.phase==='reach')robot.reach('r',room.targets[action.target].position,Math.min(1,action.clock/.6));
  }
  if(room.targets.stove){room.targets.stove.glow.intensity=state.stove?5:0;room.targets.stove.object.material.emissive.set(state.stove?0xd34e0b:0x000000);room.targets.stove.object.material.emissiveIntensity=state.stove?.35:0;}
  if(room.targets.tap){room.targets.tap.water.position.y=.31+state.water*.28;room.targets.tap.stream.visible=state.tap;}
  const target=nearest();$('interact').hidden=!target||modal();if(target)$('interact').lastElementChild.textContent=target.id==='phone'?(state.phone?'End the call':'Answer the phone'):target.id==='tap'?(state.tap?'Stop the water':'Fill the bath'):(state.stove?'Turn off the stove':'Turn on the stove');
  if(state.time>messageUntil)$('subtitle').textContent='';
}
function resize(){camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);}
addEventListener('resize',resize);
setRoom('living');
renderer.setAnimationLoop(()=>{
  const now=performance.now(),elapsed=Math.min((now-previousTime)/1000,.2);previousTime=now;
  const dt=Math.max(.0001,elapsed);
  if(entered){
    // Fixed maximum movement step also handles slow frames without tunnelling.
    const steps=Math.ceil(dt/(1/30)),step=dt/steps;
    for(let i=0;i<steps;i++){state.tick(step);updatePlayer(step);updateAgent(step);}
    updateVisuals(dt);updateCamera(dt);
  }
  else {if(human){human.update(player,dt);robot.update(companion,dt);}}
  renderer.render(scene,camera);
});
Promise.all(['human','companion'].map(name=>loader.loadAsync(new URL('models/'+name+'.glb',document.baseURI).href))).then(([a,b])=>{
  human=new Avatar(a,1.72);robot=new Avatar(b,1.55);$('load-status').textContent='Six spaces. One companion. Your move.';$('enter').disabled=false;
}).catch(error=>{$('load-status').textContent='Character assets could not load. Refresh to retry.';console.error(error);});
$('enter').onclick=()=>{entered=true;$('loading').hidden=true;previousTime=performance.now();};
document.addEventListener('visibilitychange',()=>{previousTime=performance.now();pressed.clear();stick={x:0,z:0};});
// Read-only engineering diagnostics are opt-in and never a model observation.
if(new URLSearchParams(location.search).has('debug'))window.vistaDebug=()=>({room:state.room,player:player.position.toArray(),companion:companion.position.toArray(),third,state:JSON.parse(JSON.stringify(state)),action,drawCalls:renderer.info.render.calls,triangles:renderer.info.render.triangles,assetsReady:!!human,colliders:room.colliders});

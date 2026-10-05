import * as T from 'three';
import {RoundedBoxGeometry} from 'three/addons/geometries/RoundedBoxGeometry.js';
import {ROOMS} from './simulation.js';

export function buildRoom(scene,id) {
  const group=new T.Group();scene.add(group);const colliders=[],targets={},walls=[];
  const mat=(color,roughness=.75,metalness=0)=>new T.MeshStandardMaterial({color,roughness,metalness});
  const oak=mat(0xae8760),darkWood=mat(0x674d36),white=mat(0xe8e2d7),dark=mat(0x27342e),metal=mat(0xa8b7af,.25,.8),accent=mat(ROOMS.find(r=>r.id===id).accent);
  const box=(x,y,z,w,h,d,m=white,round=.03)=>{
    const mesh=new T.Mesh(round?new RoundedBoxGeometry(w,h,d,2,Math.min(round,Math.min(w,h,d)/3)):new T.BoxGeometry(w,h,d),m);
    mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;
  };
  const solid=(x,z,w,d)=>colliders.push({x,z,w,d});
  const cylinder=(x,y,z,r,h,m)=>{const o=new T.Mesh(new T.CylinderGeometry(r,r,h,24),m);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;group.add(o);return o;};
  // CPU-owned texels survive context restoration without a second GPU canvas.
  const texels=new Uint8Array(256*64*4);
  for(let y=0;y<64;y++)for(let x=0;x<256;x++){
    const grain=Math.sin(y*2.8+Math.sin(x*.025)*1.4)*6+Math.sin(y*17+x*.13)*3,i=(y*256+x)*4;
    texels[i]=189+grain;texels[i+1]=157+grain;texels[i+2]=119+grain;texels[i+3]=255;
  }
  const texture=new T.DataTexture(texels,256,64);texture.needsUpdate=true;texture.magFilter=T.LinearFilter;texture.minFilter=T.LinearFilter;texture.wrapS=texture.wrapT=T.RepeatWrapping;texture.repeat.set(3,10);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;
  const floorMaterial=id==='bathroom'?mat(0xb6bdb7):new T.MeshStandardMaterial({map:texture,roughness:.67});
  box(0,-.09,0,8.3,.18,7.3,floorMaterial,0);
  for(let z=-3.5;z<=3.5;z+=.58)box(0,.003,z,8,.006,.009,mat(id==='bathroom'?0x8e9992:0x9b805f),0);
  if(id==='bathroom')for(let x=-4;x<=4;x+=.6)box(x,.004,0,.009,.006,7,mat(0x8e9992),0);
  for(const [x,z,w,d] of [[-4,0,.16,7.2],[0,-3.55,8.1,.16],[4,0,.16,7.2]]){
    const wall=box(x,1.7,z,w,3.4,d,white,0);walls.push(wall);solid(x,z,w,d);
    box(x,.065,z,w+.04,.13,d+.04,white,.005);
  }
  // A full-height window occupies an actual opening in the front facade.
  for(const x of [-3.6,-2.3,2.3,3.6]){
    box(x,1.7,3.55,.065,3.4,.10,darkWood,.01);
  }
  box(0,3.35,3.55,8,.13,.15,darkWood);
  box(0,3.34,0,8,.1,.15,oak);
  const rugMat=mat(id==='bedroom'?0xc7c0ae:0xa3a795);
  if(id!=='bathroom')box(0,.012,.1,4,.018,3.2,rugMat,.03);
  function plant(x,z,scale=1){
    cylinder(x,.25*scale,z,.22*scale,.50*scale,mat(0x9e927c));
    for(let i=0;i<9;i++){
      const angle=i*2.4,h=.55+(i%4)*.18;
      cylinder(x,.6*scale,z,.015*scale,.7*scale,darkWood);
      const leaf=new T.Mesh(new T.SphereGeometry(1,12,8),mat(i%2?0x536e45:0x728458));
      leaf.scale.set(.25*scale,.08*scale,.12*scale);leaf.position.set(x+Math.cos(angle)*.18*scale,h*scale,z+Math.sin(angle)*.18*scale);leaf.rotation.set(.3,angle,.3);leaf.castShadow=true;group.add(leaf);
    }
    solid(x,z,.45*scale,.45*scale);
  }
  function table(x,z,w=1.5,d=.8,height=.78){
    box(x,height,z,w,.09,d,oak);for(const a of [-1,1])for(const b of [-1,1])box(x+a*(w/2-.10),height/2,z+b*(d/2-.10),.055,height,.055,darkWood);
    solid(x,z,w,d);
  }
  function chair(x,z){box(x,.46,z,.55,.1,.52,accent);box(x,.84,z-.22,.55,.62,.08,accent);for(const a of [-1,1])for(const b of [-1,1])box(x+a*.21,.23,z+b*.19,.045,.46,.045,darkWood);solid(x,z,.58,.6);}
  function books(x,y,z,count=5){for(let i=0;i<count;i++)box(x+i*.055,y,z,.044,.15+(i%3)*.025,.13,mat([0x535d4e,0xc5a077,0x717f87,0xab6c52][i%4]),.005);}
  function phone(x,y,z){const mesh=box(x,y,z,.075,.015,.15,dark,.012);box(x,y+.009,z,.065,.002,.132,mat(0x688f83,.3),.005);targets.phone={position:new T.Vector3(x,y,z),label:'Answer the phone',object:mesh};}
  function picture(x,y,z,w=1.2,h=.8){box(x,y,z,w+.08,h+.08,.05,oak);box(x,y,z+.031,w,h,.012,mat(0xc2c5b0),0);box(x-.12,y-.03,z+.042,w*.6,h*.32,.004,accent,0);}
  const bulbs=[];
  function lamp(x,z){cylinder(x,.03,z,.23,.06,dark);cylinder(x,.76,z,.017,1.5,metal);const shade=new T.Mesh(new T.ConeGeometry(.33,.40,32,1,true),new T.MeshStandardMaterial({color:0xe5dac1,side:T.DoubleSide}));shade.position.set(x,1.52,z);group.add(shade);const light=new T.PointLight(0xffd49a,5,4,2);light.position.set(x,1.35,z);group.add(light);bulbs.push(light);}
  if(id==='living'){
    box(-2.4,.37,-.65,1.03,.44,2.8,accent);box(-2.78,.85,-.65,.24,.78,2.85,accent);for(const z of [-1.95,.65])box(-2.3,.64,z,1.05,.6,.22,accent);for(const z of [-1.3,-.05])box(-2.23,.64,z,.86,.17,1.1,mat(0x899276));solid(-2.4,-.65,1.13,2.9);
    table(-.4,-.65,1.35,.8,.43);books(-.8,.55,-.70,3);phone(-.1,.49,-.65);
    box(1.7,.38,-2.8,2.7,.7,.5,oak);solid(1.7,-2.8,2.7,.5);picture(1.7,1.65,-3.44,1.5,.8);lamp(-3,-2.7);plant(3.3,2.65,1.4);
  }else if(id==='kitchen'){
    box(0,.48,-2.8,5.8,.94,.95,accent);box(0,.98,-2.8,5.9,.08,1.02,white);solid(0,-2.8,5.9,1.02);
    for(let x=-2.4;x<3;x+=.8){box(x,.46,-2.29,.76,.78,.025,accent,.015);box(x,.75,-2.26,.26,.025,.04,metal);}
    box(-2.8,1.1,-1.4,.85,2.2,.9,metal);solid(-2.8,-1.4,.9,.95);
    const stove=box(1.15,1.04,-2.7,1,.035,.63,dark.clone());for(const x of [.89,1.4])for(const z of [-2.87,-2.52])cylinder(x,1.07,z,.095,.025,metal);
    const pan=cylinder(1.15,1.17,-2.7,.19,.17,dark);box(1.43,1.18,-2.7,.34,.035,.04,dark);
    const glow=new T.PointLight(0xff902b,0,2);glow.position.set(1.15,1.18,-2.7);group.add(glow);
    targets.stove={position:new T.Vector3(1.15,1.03,-2.25),approach:{x:1.15,z:-1.75},label:'Turn on the stove',object:stove,glow,pan};
    table(.0,.3,2.1,1.05);chair(-.6,1.18);phone(.55,.84,.25);plant(3.2,2.7);
  }else if(id==='bathroom'){
    const tubMat=mat(0xf1f0e8,.24);box(1.65,.3,-1.5,2.8,.55,1.30,tubMat,.16);box(1.65,.6,-2.14,2.85,.17,.14,tubMat,.06);box(1.65,.6,-.86,2.85,.17,.14,tubMat,.06);for(const x of [.27,3.03])box(x,.6,-1.5,.14,.17,1.35,tubMat,.06);solid(1.65,-1.5,2.95,1.45);
    const water=box(1.65,.35,-1.5,2.55,.015,1.08,new T.MeshPhysicalMaterial({color:0x91c6ba,roughness:.17,metalness:.2,transparent:true,opacity:.86}),.09);
    cylinder(.38,.91,-1.9,.028,.56,metal);box(.5,1.18,-1.9,.28,.045,.045,metal);const stream=cylinder(.62,.83,-1.9,.016,.66,mat(0xa4ddd9,.1));
    targets.tap={position:new T.Vector3(.4,.97,-.82),approach:{x:.4,z:-.2},label:'Fill the bath',water,stream};
    box(-2.6,.52,-2.4,1.55,.9,.9,oak);box(-2.6,1,-2.4,1.65,.08,.98,white);solid(-2.6,-2.4,1.7,1);cylinder(-2.6,1.06,-2.4,.28,.12,white);picture(-2.6,1.86,-3.43,1.05,.90);table(-2.3,.65,.65,.6,.5);phone(-2.3,.56,.65);plant(3,2.65);
  }else if(id==='bedroom'){
    box(-.6,.28,-1.15,2.1,.4,2.9,oak);box(-.6,.57,-1.15,2.06,.25,2.9,white);box(-.6,.78,-2.6,2.18,1.2,.14,accent);box(-.6,.72,-.55,2.06,.06,1.5,accent);for(const x of [-1.15,-.05])box(x,.75,-2.02,.85,.2,.5,mat(0xe5dbc5),.08);solid(-.6,-1.15,2.2,3);table(1.1,-2.05,.65,.6,.54);phone(1.1,.60,-2.05);box(2.9,1.15,-1.75,1.3,2.3,1.8,white);solid(2.9,-1.75,1.35,1.85);lamp(-2.5,-2.7);plant(3.1,2.65,1.25);
  }else if(id==='office'){
    table(0,-1.65,2.1,.85);box(0,1.13,-1.83,.08,.55,.08,metal);box(0,1.41,-1.85,1.02,.64,.06,dark);box(0,1.41,-1.808,.95,.57,.008,mat(0x668a80,.5),0);chair(0,-.6);phone(.7,.84,-1.5);books(-.8,.93,-1.8,5);
    for(let y=.15;y<2.4;y+=.5){box(-2.95,y,-1.45,1.15,.045,2.3,oak);books(-3.25,y+.12,-2,6);}for(const x of [-3.53,-2.36])box(x,1.15,-1.45,.06,2.4,2.3,darkWood);solid(-2.95,-1.45,1.2,2.35);plant(3.1,2.7,1.3);picture(1.85,1.65,-3.44,.9,1.2);
  }else{
    box(-2.6,.30,-1.1,1,.45,2.5,oak);box(-2.6,.57,-1.1,.96,.13,2.46,accent);solid(-2.6,-1.1,1.1,2.6);table(1.6,-2.85,2,.48);phone(1.8,.84,-2.8);cylinder(1.1,.855,-2.78,.10,.06,metal);picture(1.6,1.70,-3.44,1.2,1.1);plant(3,2.6,1.6);lamp(-3,-2.8);
  }
  return {group,colliders,targets,walls,dispose(){const materials=new Set();group.traverse(o=>{o.geometry?.dispose();if(o.material)for(const m of [o.material].flat())materials.add(m);});for(const m of materials)m.dispose();texture.dispose();scene.remove(group);}};
}

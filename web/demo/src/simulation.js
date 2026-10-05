export const ROOMS = [
  {id:'living',name:'The living room',description:'A little room for everyday life.',accent:0x6d7d60},
  {id:'entry',name:'The entrance',description:'A pause before the day begins.',accent:0x94724c},
  {id:'kitchen',name:'The kitchen',description:'Small distractions. Real decisions.',accent:0x727f6b},
  {id:'bedroom',name:'The bedroom',description:'A quiet space, with someone nearby.',accent:0x91816d},
  {id:'office',name:'The study',description:'Stay focused. Let a companion notice.',accent:0x627b7b},
  {id:'bathroom',name:'The bathroom',description:'A running bath. An unexpected call.',accent:0x798d88},
];
export function parseScenario(text) {
  if(typeof text!=='string' || text.length>600)return {supported:false};
  const t=text.toLowerCase();
  const phone=/phone|call|電話|通話/.test(t),bath=/bath|tap|water|浴|水/.test(t),stove=/stove|cook|火|爐|煮/.test(t);
  if(bath&&stove)return {supported:false,reason:'This preview supports one room at a time. Try a phone call with either the bath or stove.'};
  if(bath)return {supported:true,room:'bathroom',phone,bath:true,stove:false};
  if(stove)return {supported:true,room:'kitchen',phone,bath:false,stove:true};
  if(/follow|explor|walk|跟|走|探索/.test(t))return {supported:true,room:'living',phone:false,bath:false,stove:false};
  return {supported:false,reason:'Try “on a phone call while the bath is filling”, “left the stove on”, or “follow me”.'};
}
export function blocked(x,z,boxes,radius=.28) {
  if(Math.abs(x)>3.65 || Math.abs(z)>3.12)return true;
  return boxes.some(b=>x>b.x-b.w/2-radius&&x<b.x+b.w/2+radius&&z>b.z-b.d/2-radius&&z<b.z+b.d/2+radius);
}
export function slideMove(position,dx,dz,boxes,radius=.28) {
  // Bound each substep to prevent tunnelling through thin fixtures.
  const n=Math.max(1,Math.ceil(Math.hypot(dx,dz)/.08));
  for(let i=0;i<n;i++){
    if(!blocked(position.x+dx/n,position.z,boxes,radius))position.x+=dx/n;
    if(!blocked(position.x,position.z+dz/n,boxes,radius))position.z+=dz/n;
  }
}
export function findPath(start,goal,boxes) {
  const step=.25,toGrid=p=>[Math.round((p.x+3.5)/step),Math.round((p.z+3)/step)];
  const point=([x,z])=>({x:x*step-3.5,z:z*step-3}),key=([x,z])=>x+','+z;
  const s=toGrid(start),g=toGrid(goal),open=[{p:s,c:0}],cost=new Map([[key(s),0]]),parent=new Map();
  let end=null,iterations=0;
  while(open.length&&iterations++<1600){
    open.sort((a,b)=>(a.c+Math.hypot(a.p[0]-g[0],a.p[1]-g[1]))-(b.c+Math.hypot(b.p[0]-g[0],b.p[1]-g[1])));
    const current=open.shift(),k=key(current.p);
    if(current.c!==cost.get(k))continue;
    if(Math.hypot(current.p[0]-g[0],current.p[1]-g[1])<1.5){end=current.p;break;}
    for(const [dx,dz] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,1],[1,-1],[-1,-1]]){
      const next=[current.p[0]+dx,current.p[1]+dz],p=point(next);
      if(blocked(p.x,p.z,boxes,.34))continue;
      if(dx&&dz&&(blocked(point([next[0],current.p[1]]).x,point(current.p).z,boxes,.34)||blocked(point(current.p).x,point([current.p[0],next[1]]).z,boxes,.34)))continue;
      const c=current.c+Math.hypot(dx,dz),nk=key(next);
      if(c<(cost.get(nk)??Infinity)){cost.set(nk,c);parent.set(nk,current.p);open.push({p:next,c});}
    }
  }
  if(!end)return [];
  const result=[];
  while(key(end)!==key(s)){result.unshift(point(end));end=parent.get(key(end));if(!end)return [];}
  return result;
}
export class WorldState {
  constructor(){this.reset('living');}
  reset(room){
    this.room=room;this.time=0;this.phone=false;this.stove=false;this.tap=false;this.water=.15;
    this.assistance=true;this.action=null;this.outcome='';this.events=[];this.version=(this.version??0)+1;
  }
  stage(spec){
    if(!spec.supported)throw new Error('Unsupported scenario');
    this.reset(spec.room);this.phone=spec.phone;this.tap=spec.bath;this.stove=spec.stove;
    this.events.push({time:0,type:'scenario_started',source:'local_scripted_preview'});
  }
  tick(dt){
    this.time+=dt;
    if(this.tap)this.water=Math.min(1,this.water+dt*.012);
    if(this.water>=1&&!this.outcome){this.outcome='overflow';this.events.push({time:this.time,type:'overflow'});}
  }
  intention(){
    if(!this.assistance)return null;
    if(this.stove&&this.time>4)return {target:'stove',line:'The stove is still on. I’ll turn it off.'};
    if(this.tap&&this.water>.31)return {target:'tap',line:this.phone?'The bath is filling while you’re on the call. I’ll stop the water.':'The bath is still filling. I’ll stop the water.'};
    return null;
  }
  complete(target){
    if(target==='stove'&&this.stove)this.stove=false;
    else if(target==='tap'&&this.tap)this.tap=false;
    else return false;
    this.events.push({time:this.time,type:'control_operated',target,source:'scripted_proximity_action'});
    return true;
  }
}

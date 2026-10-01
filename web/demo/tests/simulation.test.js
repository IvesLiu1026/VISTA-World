import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseScenario,WorldState,blocked,slideMove,findPath} from '../src/simulation.js';
test('unsupported NL stays unsupported and supported multilingual input is explicit',()=>{
  assert.equal(parseScenario('Build a hospital and simulate surgery').supported,false);
  assert.equal(parseScenario('我在講電話，浴缸正在放水').room,'bathroom');
  assert.equal(parseScenario('bath and stove').supported,false);
});
test('large movement steps cannot tunnel through furniture',()=>{
  const p={x:-2,z:0},boxes=[{x:0,z:0,w:.1,d:2}];slideMove(p,4,0,boxes);
  assert.ok(p.x<-.3);assert.equal(blocked(p.x,p.z,boxes),false);
});
test('path routes around obstacles without clipping corners',()=>{
  const boxes=[{x:0,z:0,w:1.5,d:2}],path=findPath({x:-2,z:0},{x:2,z:0},boxes);
  assert.ok(path.length>10);assert.ok(path.some(p=>Math.abs(p.z)>1.3));
  assert.ok(path.every(p=>!blocked(p.x,p.z,boxes,.34)));
});
test('operating the tap changes the simulated consequence; disabling help preserves the event',()=>{
  const w=new WorldState();w.stage(parseScenario('on a phone call while bath fills'));
  for(let i=0;i<40;i++)w.tick(.5);
  assert.equal(w.intention().target,'tap');w.assistance=false;assert.equal(w.intention(),null);
  w.complete('tap');const before=w.water;w.tick(200);assert.equal(w.water,before);assert.equal(w.outcome,'');
  w.reset('bathroom');w.tap=true;w.tick(100);assert.equal(w.outcome,'overflow');
});
test('room reset changes action generation and clears all temporary events',()=>{
  const w=new WorldState(),old=w.version;w.stove=true;w.phone=true;w.reset('living');
  assert.equal(w.version,old+1);assert.equal(w.stove,false);assert.equal(w.phone,false);assert.deepEqual(w.events,[]);
});

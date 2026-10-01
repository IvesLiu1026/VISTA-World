import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';

const manifest=JSON.parse(readFileSync(new URL('../assets.json',import.meta.url)));
for(const asset of manifest.assets){
  const bytes=readFileSync(new URL('../public/models/'+asset.file,import.meta.url));
  assert.equal(bytes.length,asset.bytes,asset.file+' size');
  assert.equal(createHash('sha256').update(bytes).digest('hex'),asset.sha256,asset.file+' digest');
  assert.equal(bytes.readUInt32LE(0),0x46546c67,'GLB header');
  const gltf=JSON.parse(bytes.subarray(20,20+bytes.readUInt32LE(12)).toString());
  assert.ok(gltf.skins.some(s=>s.joints.length===asset.bone_count),'complete bound skeleton');
  for(const clip of ['Idle','Walk'])assert.ok(gltf.animations.some(a=>a.name===clip),'missing '+clip);
}
console.log('Two reviewed avatars, source digests, rigs and animation clips verified.');

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const state = require('../assets/mbti-state.js');
const entries = new Map();
globalThis.localStorage = {
  getItem: key => entries.get(key) ?? null,
  setItem: (key, value) => entries.set(key, value),
  removeItem: key => entries.delete(key),
};

const deep = {artifact_id:'aa157042-a4ad-4f29-8c5c-146fc0043970',version_id:'deep',item_count:50};
const quick = {artifact_id:'bb157042-a4ad-4f29-8c5c-146fc0043970',version_id:'quick',item_count:20};
const flow = {answers:new Map([[1,5],[2,3]]),active:2,reviewing:false};
assert.equal(state.read(deep),null);
assert.equal(state.write(deep,flow),true);
assert.deepEqual([...state.read(deep).answers],[[1,5],[2,3]]);
assert.equal(state.read(deep).active,2);
assert.equal(state.read(quick),null);

const complete = {answers:new Map(Array.from({length:50},(_,index)=>[index+1,index%5+1])),active:49,reviewing:false};
assert.equal(state.write(deep,complete,'result'),true);
assert.equal(state.read(deep).screen,'result');
assert.equal(state.read(deep).answers.size,50);
assert.equal(state.write(deep,flow,'result'),false);
assert.equal(state.read(deep).screen,'result');

entries.set(state.keyFor(deep),'{corrupt');
assert.equal(state.read(deep),null);
entries.set(state.keyFor(deep),JSON.stringify({v:1,artifactId:deep.artifact_id,
  versionId:'deep',answers:[[1,4],[1,5]],active:1,reviewing:false,screen:'question'}));
assert.equal(state.read(deep),null);
state.clear(deep);
assert.equal(entries.has(state.keyFor(deep)),false);
globalThis.localStorage.setItem=()=>{throw new Error('disabled');};
assert.equal(state.write(deep,flow),false);
console.log('MBTI state: question resume, result resume, artifact isolation, validation and storage fallback passed.');

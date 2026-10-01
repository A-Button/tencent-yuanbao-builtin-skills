import assert from 'node:assert/strict';
import { createAnimationLoop } from '../assets/tarot-studio-source/animation-loop.js';

let id = 0, failNext = false;
const pending = new Map(), deltas = [];
const loop = createAnimationLoop(dt => {
  if (failNext) { failNext = false; throw new Error('transient canvas failure'); }
  deltas.push(dt);
}, callback => { pending.set(++id, callback); return id; }, token => pending.delete(token));
function frame(time) {
  assert.equal(pending.size, 1, 'exactly one background frame may be pending');
  const [token, callback] = pending.entries().next().value;
  pending.delete(token); callback(time);
}
loop.start(); loop.start();
frame(1000); frame(1016);
assert.deepEqual(deltas, [0, .016]);
// A temporary drawing failure must not leave the whole background frozen.
failNext = true;
assert.throws(() => frame(1032), /transient canvas failure/);
frame(1048);
assert.equal(deltas.at(-1), .016);
// Hiding/restoring the page must neither duplicate loops nor jump through lost time.
loop.stop(); assert.equal(pending.size, 0);
loop.start(); loop.start(); frame(50000); frame(50016);
assert.deepEqual(deltas.slice(-2), [0, .016]);
frame(90000); assert.equal(deltas.at(-1), .05);
loop.stop(); loop.stop(); assert.equal(pending.size, 0);
console.log(JSON.stringify({ok:true, singleLoop:true, resumesAfterVisibility:true, survivesFrameError:true, cleanup:true}));

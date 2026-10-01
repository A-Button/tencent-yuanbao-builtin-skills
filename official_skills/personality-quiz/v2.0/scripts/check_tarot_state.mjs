import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const payload = JSON.parse(readFileSync(new URL('../assets/tarot-studio-source/tarot-presets.json', import.meta.url)));
globalThis.window = {__TAROT_DECK_DATA__: payload, location: {hash: ''}};
const entries = new Map();
globalThis.localStorage = {
  getItem: key => entries.get(key) ?? null,
  setItem: (key, value) => entries.set(key, value),
  removeItem: key => entries.delete(key),
};

const {createDeck} = await import('../assets/tarot-studio-source/tarot-data.js');
const state = await import('../assets/tarot-studio-source/artifact-state.js');
const first = 'aa157042-a4ad-4f29-8c5c-146fc0043970';
const second = 'bb157042-a4ad-4f29-8c5c-146fc0043970';
const deck = createDeck(() => 0.37);
assert.equal(state.readLocalState(first), null);
assert.equal(state.saveLocalState(first, deck, [4, 18]), true);
const restored = state.readLocalState(first);
assert.deepEqual(restored.used, [4, 18]);
assert.deepEqual(restored.revealed, [0, 1]);
assert.deepEqual(restored.selected.map(card => [card.id, card.reversed]),
  [deck[4], deck[18]].map(card => [card.id, card.reversed]));
assert.equal(state.readLocalState(second), null);

const cards = [deck[4], deck[18], deck[29]];
const snapshot = state.makeShareSnapshot(first, cards);
assert.deepEqual(state.readShareSnapshot(snapshot, first).selected.map(card => [card.id, card.reversed]),
  cards.map(card => [card.id, card.reversed]));
assert.equal(state.readShareSnapshot(snapshot, second), null);
assert.equal(state.makeShareSnapshot(first, cards.slice(0, 2)), null);
window.location.hash = '#tarot-state=' + Buffer.from(JSON.stringify(snapshot)).toString('base64url');
assert.deepEqual(state.readShareFragment(first).selected.map(card => card.id), cards.map(card => card.id));
window.location.hash = '#tarot-state=invalid';
assert.equal(state.readShareFragment(first), null);

entries.set(state.storageKey(first), '{bad json');
assert.equal(state.readLocalState(first), null);
state.clearLocalState(first);
assert.equal(entries.has(state.storageKey(first)), false);
globalThis.localStorage.setItem = () => {throw new Error('blocked');};
assert.equal(state.saveLocalState(first, deck, [4]), false);
console.log('Tarot state: local restore, artifact isolation, share snapshot, fragment and storage fallback passed.');

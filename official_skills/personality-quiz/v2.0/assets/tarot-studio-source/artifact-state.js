import { createDeck } from './tarot-data.js';

const VERSION = 1;
const PREFIX = 'yuanbao:tarot:state:v1:';
const CARD_COUNT = 78;

export function storageKey(artifactId) {
  return PREFIX + artifactId;
}

function validId(value) {
  return typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function validCards(cards) {
  return Array.isArray(cards) && cards.length <= 3 && cards.every(card =>
    card && typeof card.id === 'string' && typeof card.reversed === 'boolean'
  ) && new Set(cards.map(card => card.id)).size === cards.length;
}

export function cardFromRecord(record, deck) {
  const source = deck.find(card => card.id === record.id);
  if (!source) return null;
  return {
    ...source,
    reversed: record.reversed,
    text: record.reversed ? source.displayReversed : source.displayUpright,
    meaning: record.reversed ? source.meaningReversed : source.meaningUpright,
  };
}

export function readLocalState(artifactId) {
  if (!validId(artifactId)) return null;
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(artifactId)) || 'null');
    if (!saved || saved.v !== VERSION || saved.artifactId !== artifactId ||
        !Number.isFinite(saved.updatedAt) ||
        !Array.isArray(saved.deck) || saved.deck.length !== CARD_COUNT ||
        !saved.deck.every(record => Array.isArray(record) && typeof record[0] === 'string' &&
          (record[1] === 0 || record[1] === 1)) ||
        new Set(saved.deck.map(record => record[0])).size !== CARD_COUNT ||
        !Array.isArray(saved.used) || saved.used.length > 3 ||
        !saved.used.every(index => Number.isInteger(index) && index >= 0 && index < CARD_COUNT) ||
        new Set(saved.used).size !== saved.used.length ||
        !Array.isArray(saved.revealed) || saved.revealed.some(index => !Number.isInteger(index) || index < 0 || index >= saved.used.length)) return null;
    const fresh = createDeck();
    const deck = saved.deck.map(([id, reversed]) => cardFromRecord({id, reversed: Boolean(reversed)}, fresh));
    if (deck.some(card => !card)) return null;
    const selected = saved.used.map(index => deck[index]);
    // An interrupted card animation resumes at its next stable point.
    return {deck, used: saved.used, selected, revealed: selected.map((_, index) => index)};
  } catch {
    return null;
  }
}

export function saveLocalState(artifactId, deck, used) {
  if (!validId(artifactId)) return false;
  try {
    localStorage.setItem(storageKey(artifactId), JSON.stringify({
      v: VERSION, artifactId, updatedAt: Date.now(),
      deck: deck.map(card => [card.id, card.reversed ? 1 : 0]),
      used: [...used], revealed: used.map((_, index) => index),
    }));
    return true;
  } catch {
    return false;
  }
}

export function clearLocalState(artifactId) {
  if (!validId(artifactId)) return;
  try { localStorage.removeItem(storageKey(artifactId)); } catch { /* Storage may be disabled. */ }
}

export function makeShareSnapshot(artifactId, selected) {
  if (!validId(artifactId) || !validCards(selected) || selected.length !== 3) return null;
  return {v: VERSION, kind: 'tarot-result', artifactId,
    cards: selected.map(card => ({id: card.id, reversed: card.reversed}))};
}

export function readShareSnapshot(value, artifactId) {
  if (!value || value.v !== VERSION || value.kind !== 'tarot-result' ||
      value.artifactId !== artifactId || !validCards(value.cards) || value.cards.length !== 3) return null;
  const fresh = createDeck();
  const selected = value.cards.map(record => cardFromRecord(record, fresh));
  if (selected.some(card => !card)) return null;
  return {deck: fresh, selected, used: [], revealed: [0, 1, 2]};
}

export function readShareFragment(artifactId) {
  const match = /^#tarot-state=([A-Za-z0-9_-]{1,2048})$/.exec(window.location.hash);
  if (!match) return null;
  try {
    const bytes = Uint8Array.from(atob(match[1].replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    return readShareSnapshot(JSON.parse(new TextDecoder().decode(bytes)), artifactId);
  } catch { return null; }
}

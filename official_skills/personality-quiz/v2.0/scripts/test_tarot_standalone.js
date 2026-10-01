#!/usr/bin/env node
// Test the integrated studio deck and conversation handoff without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const html = fs.readFileSync(process.argv[2], 'utf8');
function embedded(pattern) {
  const match = html.match(pattern);
  assert.ok(match, String(pattern));
  return JSON.parse(match[1]);
}
const deck = embedded(/window\.__TAROT_DECK_DATA__ = (\{.*?\});<\/script>/s);
const assets = embedded(/window\.__TAROT_ASSETS__ = (\{.*?\});<\/script>/s);
const config = embedded(/<script id="tarot-standalone-config" type="application\/json">(.*?)<\/script>/s);
global.window = { __TAROT_DECK_DATA__: deck, __TAROT_ASSETS__: assets };
const source = path.resolve(__dirname, '../assets/tarot-studio-source');
const appSource = fs.readFileSync(path.join(source, 'App.jsx'), 'utf8');
const cssSource = fs.readFileSync(path.join(source, 'styles.css'), 'utf8') +
  fs.readFileSync(path.join(source, 'tarot-table.css'), 'utf8') +
  fs.readFileSync(path.join(source, 'deck-motion.css'), 'utf8') +
  fs.readFileSync(path.join(source, 'atmosphere.css'), 'utf8');

async function main() {
  const tarot = await import(pathToFileURL(path.join(source, 'tarot-data.js')));
  const { formatHandoff, copyHandoff } = await import(pathToFileURL(path.join(source, 'handoff.js')));
  assert.equal(deck.cards.length, 78);
  assert.equal(Object.keys(assets).length, 80);
  assert.ok(appSource.includes('分享结果'));
  assert.ok(appSource.includes('const total=3'));
  assert.ok(!/纸上星图|生成分享海报|spread-options|position-label|position-inline/.test(appSource));
  assert.ok(!cssSource.includes('.paper'));
  assert.ok(!Object.keys(assets).some(name => name.startsWith('paper-')));
  assert.ok(config.question);
  const seq = [0.1, 0.8, 0.4, 0.9, 0.3, 0.7];
  let at = 0;
  const cards = tarot.createDeck(() => seq[at++ % seq.length]);
  assert.equal(cards.length, 78);
  assert.equal(new Set(cards.map(card => card.id)).size, 78);
  assert.ok(cards.some(card => card.reversed));
  assert.ok(cards.some(card => !card.reversed));
  for (const card of cards) {
    assert.equal(card.text, card.reversed ? card.displayReversed : card.displayUpright);
    assert.equal(tarot.cardArt(card), assets[`${card.symbolId}.webp`]);
  }
  const selected = cards.slice(0, 3);
  const handoff = formatHandoff(config.question, tarot.spreads['three-card'], selected);
  assert.ok(handoff.includes(config.question));
  assert.ok(!/位次含义|时间之流|情况 · 障碍 · 建议/.test(handoff));
  assert.ok(handoff.includes('第1张：'));
  for (const card of selected) assert.ok(handoff.includes(card.title));
  assert.ok(!handoff.includes(cards[3].title), 'unselected card stays out of handoff');

  let legacyCopies = 0;
  const clipboard = { writeText: async () => { throw Error('blocked'); } };
  const doc = {
    body: { appendChild() {} },
    createElement: () => ({ style: {}, focus() {}, select() {}, remove() {} }),
    execCommand: () => { legacyCopies++; return true; },
  };
  assert.equal(await copyHandoff(handoff, clipboard, doc), true);
  assert.equal(legacyCopies, 1);
  doc.execCommand = () => false;
  assert.equal(await copyHandoff(handoff, clipboard, doc), false);
  console.log(JSON.stringify({ ok: true, cards: 78, orientations: 2, assets: 80,
    handoff: true, legacyCopies }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });

// The Skill's tarot_deck.py is the only deck source. The standalone packager
// embeds its exact payload before the application bundle runs.
const presets = window.__TAROT_DECK_DATA__;
if (!presets || !Array.isArray(presets.cards) || presets.cards.length !== 78) {
  throw new Error('塔罗牌库未正确载入');
}

export const spreads = presets.spreads;
export const tarotMetadata = {
  tradition: presets.tradition,
  version: presets.contentVersion,
  source: presets.sourceLabel,
  editorialNotice: presets.editorialNotice,
};
export const assetUrl = name => window.__TAROT_ASSETS__[name];
export const cardArt = card => assetUrl(`${card.symbolId}.webp`);
export const orientationLabel = card => card.reversed ? '逆位' : '正位';

// Seal all 78 cards once per round. Moving the wheel never changes a card.
export function createDeck(random = Math.random) {
  const deck = presets.cards.map(card => {
    const reversed = random() < presets.drawPolicy.reversalRate;
    return {
      ...card, id: card.cardId, title: card.nameZh, reversed,
      phrase: card.keywords.slice(0, 2).join(' · '),
      text: reversed ? card.displayReversed : card.displayUpright,
      meaning: reversed ? card.meaningReversed : card.meaningUpright,
      question: card.reflectionQuestions[0],
    };
  });
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

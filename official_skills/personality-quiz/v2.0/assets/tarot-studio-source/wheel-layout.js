// Reserve the full rotating card bounds, including the shuffle scatter.
export function wheelGeometry(width, cardWidth) {
  const radius = Math.max(670, width * 3.6);
  const cardHeight = cardWidth * 1.75;
  const halfDiagonal = Math.hypot(cardWidth, cardHeight) / 2;
  const scatterScale = Math.max(.25, Math.min(cardWidth / 132, (width / 2 - halfDiagonal - 40) / 105));
  const scatterY = 105 * .45 * scatterScale;
  const top = Math.ceil(halfDiagonal - cardHeight / 2 + scatterY + 24);
  const edgeAngle = Math.asin(Math.min(cardWidth / 132, (width / 2 + cardWidth) / radius));
  const arcY = radius * (1 - Math.cos(edgeAngle));
  const bottomTravel = Math.max(arcY, arcY * .03 + scatterY);
  const height = Math.ceil(top + cardHeight / 2 + bottomTravel + halfDiagonal + 24);
  return { cardWidth, radius, step: cardWidth * .57 / radius, scatterScale, fanAngle: edgeAngle, top, height };
}

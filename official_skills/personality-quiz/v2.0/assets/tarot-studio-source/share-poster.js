// Draw decoded card bitmaps directly, avoiding nested images in SVG foreignObject.
export async function loadPosterImage(src) {
  if (!src) throw new Error('Missing card artwork');
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error('Card artwork failed to load'));
    img.src = src;
  });
  await img.decode();
  if (!img.naturalWidth || !img.naturalHeight) throw new Error('Empty card artwork');
  return img;
}

export function wrapPosterText(ctx, text, width) {
  const lines = [];
  let line = '';
  for (const char of String(text)) {
    if (char === '\n') { lines.push(line); line = ''; continue; }
    if (line && ctx.measureText(line + char).width > width) {
      lines.push(line); line = char;
    } else line += char;
  }
  if (line) lines.push(line);
  return lines;
}

export async function renderSharePoster(cards, artForCard, labelForCard) {
  if (cards.length !== 3) throw new Error('Expected three cards');
  await document.fonts.load('400 18px "Noto Serif SC"');
  await document.fonts.ready;
  // Fail the whole export if any card is missing; never cache a partial poster.
  const images = await Promise.all(cards.map(card => loadPosterImage(artForCard(card))));
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas unavailable');
  const width = 720, padding = 52, gap = 20, column = (width - padding * 2 - gap * 2) / 3;
  const imageTop = 222, imageHeight = column * 7 / 4;
  const textTop = imageTop + imageHeight + 104, lineHeight = 34.2;
  const font = size => `400 ${size}px "Noto Serif SC", "Songti SC", serif`;
  ctx.font = font(18);
  const lines = cards.map(card => wrapPosterText(ctx, card.text, column));
  const height = Math.ceil(Math.max(1000, textTop + Math.max(...lines.map(value => value.length)) * lineHeight + 60));
  const ratio = 1.5;
  canvas.width = Math.ceil(width * ratio); canvas.height = Math.ceil(height * ratio);
  ctx.scale(ratio, ratio);
  ctx.fillStyle = '#10120f'; ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = '#b99a6259'; ctx.lineWidth = 1; ctx.strokeRect(.5, .5, width - 1, height - 1);
  ctx.textBaseline = 'top'; ctx.fillStyle = '#e9d4ae'; ctx.font = font(26);
  ctx.fillText('观照', padding, 52);
  ctx.textAlign = 'right'; ctx.font = '12px Georgia, serif'; ctx.fillText('TAROT JOURNAL', width - padding, 66);
  ctx.textAlign = 'center'; ctx.font = font(36); ctx.fillText('答案，在你心中回响。', width / 2, 138);
  cards.forEach((card, index) => {
    const x = padding + index * (column + gap);
    ctx.fillStyle = '#b59a69'; ctx.fillRect(x, imageTop, column, imageHeight);
    ctx.save();
    ctx.translate(x + column / 2, imageTop + imageHeight / 2);
    if (card.reversed) ctx.rotate(Math.PI);
    ctx.drawImage(images[index], -column / 2 + 4, -imageHeight / 2 + 4, column - 8, imageHeight - 8);
    ctx.restore();
    ctx.textAlign = 'center'; ctx.fillStyle = '#e9d4ae'; ctx.font = font(24);
    ctx.fillText(card.title, x + column / 2, imageTop + imageHeight + 22, column);
    ctx.fillStyle = '#b9a98e'; ctx.font = font(15);
    ctx.fillText(labelForCard(card), x + column / 2, imageTop + imageHeight + 59);
    ctx.textAlign = 'left'; ctx.font = font(18);
    lines[index].forEach((line, row) => ctx.fillText(line, x, textTop + row * lineHeight));
  });
  const png = canvas.toDataURL('image/png');
  if (!png.startsWith('data:image/png;base64,')) throw new Error('PNG export failed');
  return png;
}

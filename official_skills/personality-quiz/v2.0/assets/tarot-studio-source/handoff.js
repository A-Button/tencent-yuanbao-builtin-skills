export function formatHandoff(question, spread, selected) {
  const lines = selected.map((card, index) => {
    const keywords = card.keywords?.length ? `，关键词：${card.keywords.join('、')}` : '';
    const archetype = card.archetype ? `，核心母题：${card.archetype}` : '';
    const structure = card.element ? `，结构：${card.element}元素 / ${card.domain || '当前生活议题'}` +
      (card.rankArchetype ? ` / ${card.rankArchetype}` : '') : '';
    const visual = card.visualSymbols?.length ? `，图像锚点：${card.visualSymbols.join('、')}` : '';
    const source = card.sourceLabel ? `，来源：${card.sourceLabel}` : '';
    return `- 第${index + 1}张：${card.title}，${card.reversed ? '逆位' : '正位'}` +
      `${keywords}，基础牌义：${card.meaning}，牌面提示：${card.text}${archetype}${structure}${visual}${source}。`;
  });
  const prefix = question ? `我问的是「${question}」，抽了三张牌。` : '我抽了三张牌。';
  return `以下是我刚刚从塔罗牌桌复制的已抽牌面信息。${prefix}\n` +
    `请按当前塔罗解读规则直接在对话中回答，不要重新抽牌。\n\n已抽牌面：\n${lines.join('\n')}`;
}

export async function copyHandoff(text, clipboard = navigator.clipboard, doc = document) {
  if (clipboard?.writeText) {
    try { await clipboard.writeText(text); return true; } catch { /* Fall through. */ }
  }
  const area = doc.createElement('textarea');
  const previous = doc.activeElement;
  area.value = text;
  area.readOnly = true;
  area.style.position = 'fixed';
  area.style.left = '-9999px';
  area.style.fontSize = '16px';
  doc.body.appendChild(area);
  area.focus(); area.select();
  let copied = false;
  try { copied = doc.execCommand('copy'); } catch { /* Show manual copy. */ }
  area.remove();
  previous?.focus?.({ preventScroll: true });
  return copied;
}

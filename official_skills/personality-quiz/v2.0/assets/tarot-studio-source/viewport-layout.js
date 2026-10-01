import { wheelGeometry } from './wheel-layout.js';

// All dimensions come from the host viewport, never from the rendered content.
export function tableLayout(width, height, hasQuestion = false) {
  const mobile = width <= 700;
  const landscape = height < 500 && width > height * 1.3;
  const header = landscape ? 44 : 52;
  const intro = landscape ? (hasQuestion ? 72 : 52) : hasQuestion ? (mobile ? 94 : 106) : (mobile ? 72 : 86);
  const caption = 44, footer = 52, gap = 8, bottom = 8;
  const wheelWidth = landscape ? Math.floor(width * .62) : Math.min(width, 1000);
  const slotMax = landscape ? Math.min(80,(width-wheelWidth-32)/3) : Math.min(mobile ? 116 : 176, (width - 48) / 3);
  const slotMin = Math.min(slotMax, 64);
  const wheelMax = mobile ? 88 : 108, wheelMin = 52;
  const candidate = factor => {
    const slot = slotMin + (slotMax - slotMin) * factor;
    const wheel = wheelGeometry(wheelWidth, wheelMin + (wheelMax - wheelMin) * factor);
    // Desktop result copy shares the same size budget and card positions as drawing.
    const lower = mobile ? wheel.height + footer : Math.max(wheel.height + footer, 210);
    const required = header + intro + (landscape ? Math.max(slot * 1.75 + caption, wheel.height + footer) : slot * 1.75 + caption + gap + lower) + bottom;
    return {width, height, mobile, landscape, header, intro, slot, caption, gap, bottom, wheelWidth, wheel, required};
  };
  let lo = 0, hi = 1;
  for (let i = 0; i < 18; i++) {
    const mid = (lo + hi) / 2;
    if (candidate(mid).required <= height - 2) lo = mid; else hi = mid;
  }
  const result = candidate(lo);
  result.fits = result.required <= height;
  result.leading = Math.min(32, Math.max(0, (height - result.required) / 2));
  return result;
}

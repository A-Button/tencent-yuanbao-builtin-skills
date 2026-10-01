import assert from 'node:assert/strict';
import { tableLayout } from '../assets/tarot-studio-source/viewport-layout.js';

// Exercise card corners during fan, gather and scatter at phone/tablet/desktop sizes.
let checked = 0;
const viewports = [[320,568],[360,640],[375,667],[390,844],[430,932],[667,375],
  [844,390],[700,800],[768,1024],[1024,768],[1366,768],[1440,900]];
for (const hasQuestion of [false,true]) for (const [viewportWidth, height] of viewports) {
  const layout = tableLayout(viewportWidth, height, hasQuestion);
  assert.ok(layout.fits, `viewport budget exceeded at ${viewportWidth}x${height}`);
  assert.ok(layout.required + layout.leading <= height);
  const width = layout.wheelWidth;
  const g = layout.wheel, w = g.cardWidth, h = w * 1.75;
  for (const [spread, scatter] of [[1,0],[.95,0],[.5,0],[.03,0],[.03,.5],[.03,1]]) {
    for (let offset = -39; offset < 39; offset += .5) {
      const theta = offset * g.step;
      const visible = spread < .95 ? Math.abs(offset) < 17 && Math.abs(theta) < g.fanAngle :
        Math.abs(theta) < Math.PI / 2 && Math.abs(g.radius * Math.sin(theta)) < width / 2 + w;
      if (!visible) continue;
      for (let a = 0; a < Math.PI * 2; a += Math.PI / 12) {
        for (const spin of [-95,0,95]) {
          const cy = g.top + h / 2 + g.radius * (1 - Math.cos(theta)) * spread + Math.sin(a) * 105 * .45 * scatter * g.scatterScale;
          const angle = theta * spread + spin * Math.PI / 180 * scatter;
          const extent = Math.abs(Math.sin(angle)) * w / 2 + Math.abs(Math.cos(angle)) * h / 2;
          assert.ok(cy - extent >= 12, `top clipping at ${width}x${height}`);
          assert.ok(cy + extent <= g.height - 12, `bottom clipping at ${width}x${height}`);
          checked++;
        }
      }
    }
  }
}
console.log(JSON.stringify({ok:true, viewports:viewports.length, questionVariants:2, checkedCardBounds:checked}));

import React, { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { assetUrl } from './tarot-data';

const COUNT = 78;
const wrap = value => ((value + COUNT / 2) % COUNT + COUNT) % COUNT - COUNT / 2;

export const TarotWheel = forwardRef(function TarotWheel(props, apiRef) {
  const stage = useRef(null), leaves = useRef([]), buttons = useRef([]), live = useRef(props);
  live.current = props;
  const control = useRef({ stop() {}, shift() {}, focus() {} });
  const phase = useRef(0);
  const scatter = useRef(Array.from({ length: COUNT }, () => ({
    a: Math.random() * Math.PI * 2, b: Math.random() * Math.PI * 2,
    r: 25 + Math.random() * 80, spin: Math.random() * 120 - 60,
  })));
  useImperativeHandle(apiRef, () => ({
    get element() { return stage.current; },
    stop: () => control.current.stop(),
    shift: direction => control.current.shift(direction),
    focusNext: () => control.current.focus(),
  }), []);

  useLayoutEffect(() => {
    const el = stage.current;
    let width = 0, cardWidth = 0, radius = 0, step = 0, scatterScale = 1, fanAngle = 0;
    let frame = 0, last = 0, velocity = 0, drag = null, shiftTween;
    const model = { spread: props.round > 0 ? .03 : 1, scatter: 0, turn: 0, opacity: 0 };
    let disposed = false;
    const animated = live.current.motion && !matchMedia('(prefers-reduced-motion: reduce)').matches;
    let intro = true;
    const isUsed = i => live.current.used.includes(i);
    function paint() {
      let nearest = -1, distance = Infinity;
      for (let i = 0; i < COUNT; i++) {
        const button = buttons.current[i], leaf = leaves.current[i];
        if (!button || !leaf) continue;
        const offset = wrap(i + phase.current), theta = offset * step;
        const visible = !isUsed(i) && (intro && model.spread < .95
          ? Math.abs(offset) < 17 && Math.abs(theta) < fanAngle : Math.abs(theta) < Math.PI / 2 && Math.abs(radius * Math.sin(theta)) < width / 2 + cardWidth);
        button.style.visibility = visible ? 'visible' : 'hidden';
        button.style.pointerEvents = visible && !live.current.busy ? 'auto' : 'none';
        button.setAttribute('aria-hidden', String(!visible));
        button.tabIndex = -1;
        if (!visible) continue;
        const s = scatter.current[i];
        const angle = s.a + model.turn * .8;
        const x = radius * Math.sin(theta) * model.spread + Math.cos(angle) * s.r * model.scatter * scatterScale;
        const y = radius * (1 - Math.cos(theta)) * model.spread + Math.sin(angle) * s.r * .45 * model.scatter * scatterScale;
        const rotation = theta * 180 / Math.PI * model.spread + (s.spin + Math.sin(model.turn * 2 + s.b) * 35) * model.scatter;
        button.style.transform = `translate3d(${x}px,${y}px,0) rotate(${rotation}deg)`;
        button.style.zIndex = String(100 + Math.round(offset + COUNT / 2));
        button.style.opacity = model.opacity;
        leaf.dataset.angle = String(rotation);
        if (Math.abs(offset) < distance) { nearest = i; distance = Math.abs(offset); }
      }
      if (nearest >= 0) buttons.current[nearest].tabIndex = live.current.busy ? -1 : 0;
    }
    function layout() {
      width = live.current.geometry.width;
      const geometry = live.current.geometry.wheel;
      ({cardWidth, radius, step, scatterScale, fanAngle} = geometry);
      el.style.setProperty('--wheel-card-width', `${cardWidth}px`);
      el.style.setProperty('--wheel-top', `${geometry.top}px`);
      el.style.height = `${geometry.height}px`;
      paint();
    }
    function stop() {
      cancelAnimationFrame(frame); frame = 0; velocity = 0;
      shiftTween?.kill();
    }
    function clearHover() {
      for (const leaf of leaves.current) leaf?.style.setProperty('--lift', '0px');
    }
    function focus() {
      paint(); el.querySelector('[tabindex="0"]')?.focus({ preventScroll: true });
    }
    function shift(direction) {
      if (live.current.busy || intro) return;
      stop(); clearHover();
      const target = { value: phase.current };
      shiftTween = gsap.to(target, {
        value: phase.current - direction, duration: live.current.motion ? .35 : 0, ease: 'power2.out',
        onUpdate: () => { phase.current = target.value; paint(); }, onComplete: focus,
      });
    }
    control.current = { stop, shift, focus, paint, layout };
    function coast(now) {
      const dt = Math.min(32, now - last); last = now;
      phase.current += velocity * dt;
      velocity *= Math.exp(-dt / 170);
      paint();
      if (Math.abs(velocity) > .00025 && !document.hidden && live.current.motion) frame = requestAnimationFrame(coast);
      else { frame = 0; velocity = 0; }
    }
    function down(event) {
      if (event.isPrimary === false || event.button !== 0 || live.current.busy || intro) return;
      stop(); clearHover();
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, phase: phase.current,
        lastX: event.clientX, time: event.timeStamp, moved: 0 };
      el.setPointerCapture(event.pointerId);
    }
    function move(event) {
      if (live.current.busy || intro) return;
      if (drag && drag.id === event.pointerId) {
        const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
        drag.moved = Math.max(drag.moved, Math.hypot(dx, dy));
        if (drag.moved > 6) el.dataset.dragging = 'true';
        const dt = event.timeStamp - drag.time;
        if (dt > 0) velocity = Math.max(-.035, Math.min(.035, (event.clientX - drag.lastX) / (cardWidth * .57) / dt));
        phase.current = drag.phase + dx / (cardWidth * .57);
        drag.lastX = event.clientX; drag.time = event.timeStamp;
        paint(); return;
      }
      if (event.pointerType === 'touch' || !live.current.motion) return;
      const hit = event.target.closest('.wheel-card');
      const index = hit ? Number(hit.dataset.index) : -100;
      for (let i = 0; i < COUNT; i++) {
        const d = Math.abs(wrap(i - index));
        leaves.current[i]?.style.setProperty('--lift', `${index === -100 ? 0 : d === 0 ? -20 : d === 1 ? -6 : 0}px`);
      }
    }
    function end(event, pick) {
      if (!drag || drag.id !== event.pointerId) return;
      const moved = drag.moved, fresh = event.timeStamp - drag.time < 90;
      drag = null; el.dataset.dragging = 'false';
      if (el.hasPointerCapture(event.pointerId)) el.releasePointerCapture(event.pointerId);
      if (!pick) { stop(); clearHover(); return; }
      if (moved <= 6) {
        const hit = document.elementFromPoint(event.clientX, event.clientY)?.closest('.wheel-card');
        if (hit && el.contains(hit)) {
          const index = Number(hit.dataset.index);
          live.current.onPick(index, { currentTarget: leaves.current[index], detail: 1 });
        }
      } else if (fresh && live.current.motion) { last = performance.now(); frame = requestAnimationFrame(coast); }
    }
    const up = e => end(e, true), cancel = e => end(e, false);
    const key = e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); shift(e.key === 'ArrowRight' ? 1 : -1); } };
    const visibility = () => { if (document.hidden) { stop(); drag = null; clearHover(); el.dataset.dragging = 'false'; } };
    layout();
    el.addEventListener('pointerdown', down); el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', cancel);
    el.addEventListener('pointerleave', clearHover); el.addEventListener('keydown', key);
    document.addEventListener('visibilitychange', visibility);
    const timeline = gsap.timeline({ paused: true, onUpdate: paint, onComplete: () => {
      intro = false; live.current.onReady(); paint();
    } });
    live.current.onBegin('gathering');
    if (!animated) timeline.to(model, { opacity: 1, spread: 1, duration: .01 });
    else {
      timeline.to(model, { opacity: 1, duration: .15 })
        .to(model, { spread: .03, duration: props.round > 0 ? .12 : .42, ease: 'power2.inOut' })
        .call(() => live.current.onStage('shuffling'))
        .to(model, { scatter: 1, turn: .4, duration: .4, ease: 'power2.out' })
        .to(model, { turn: 2.4, duration: .75, ease: 'sine.inOut' })
        .to(model, { scatter: 0, duration: .3, ease: 'power2.inOut' })
        .call(() => live.current.onStage('spreading'))
        .to(model, { spread: 1, duration: .75, ease: 'power3.out' });
    }
    const back = el.querySelector('img');
    Promise.resolve(back?.decode?.()).catch(() => {}).then(() => { if (!disposed) timeline.play(); });
    control.current.finish = () => timeline.progress(1);
    return () => {
      disposed = true;
      stop(); timeline.kill();
      el.removeEventListener('pointerdown', down); el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', cancel);
      el.removeEventListener('pointerleave', clearHover); el.removeEventListener('keydown', key);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [props.round]);

  useLayoutEffect(() => { control.current.layout?.(); }, [props.geometry]);

  useEffect(() => {
    if (props.busy) control.current.stop();
    if (!props.motion) { control.current.stop(); control.current.finish?.(); }
    control.current.paint?.();
  }, [props.used, props.busy, props.motion]);

  return <div ref={stage} className={`tarot-wheel ${props.busy ? 'is-busy' : ''}`} role="group" aria-label="78 张塔罗牌，可左右拖动或用方向键拨动">
    {Array.from({ length: COUNT }, (_, i) => <button key={i} ref={el => buttons.current[i] = el}
      className="wheel-card" data-index={i} disabled={props.busy || props.used.includes(i)}
      aria-label={`选择第 ${i + 1} 张牌`} tabIndex={-1}
      onClick={event => { if (event.detail === 0 && !props.busy) props.onPick(i, { currentTarget: leaves.current[i], detail: 0 }); }}>
      <span className="wheel-leaf" ref={el => leaves.current[i] = el}>
        <img src={assetUrl(`${props.theme}-back.jpg`)} draggable="false" alt="" />
      </span>
    </button>)}
  </div>;
});

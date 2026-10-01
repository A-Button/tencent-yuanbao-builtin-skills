import { useEffect, useRef } from 'react';
import { createAnimationLoop } from './animation-loop';
import './atmosphere.css';

// All effects live behind the interface; the exported poster stays still.
export function Atmosphere({ enabled, revealed }) {
  const root = useRef(null);
  const canvas = useRef(null);
  const emit = useRef(null);

  useEffect(() => {
    if (!enabled) return;
    const el = canvas.current, ctx = el.getContext('2d');
    if (!ctx) return;
    let width = 0, height = 0, pixelRatio = 0, time = 0, particles = [], bursts = [], lost = false;
    const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 };
    const random = (min, max) => min + Math.random() * (max - min);
    function resize(force = false) {
      const rect = root.current.getBoundingClientRect();
      const nextWidth = Math.round(rect.width), nextHeight = Math.round(rect.height);
      if (nextWidth < 1 || nextHeight < 1) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      if (!force && nextWidth === width && nextHeight === height && dpr === pixelRatio) return;
      const sx = width ? nextWidth / width : 1, sy = height ? nextHeight / height : 1;
      particles.forEach(p => { p.x *= sx; p.y *= sy; });
      bursts.forEach(p => { p.x *= sx; p.y *= sy; });
      width = nextWidth; height = nextHeight; pixelRatio = dpr;
      el.width = Math.round(width * dpr); el.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(85, Math.round(width * height / 16500));
      if (particles.length > count) particles.length = count;
      while (particles.length < count) particles.push({
        x: random(0, width), y: random(0, height), size: random(.55, 1.65),
        speed: random(5, 16), phase: random(0, Math.PI * 2), depth: random(.3, 1),
      });
    }
    function move(event) {
      if (event.pointerType === 'touch') return;
      pointer.targetX = (event.clientX / window.innerWidth - .5) * 22;
      pointer.targetY = (event.clientY / window.innerHeight - .5) * 15;
    }
    function leave() { pointer.targetX = 0; pointer.targetY = 0; }
    emit.current = index => {
      const slot = document.querySelector(`[data-slot="${index}"] .slot-face`);
      if (!slot) return;
      const a = slot.getBoundingClientRect(), b = root.current.getBoundingClientRect();
      const x = a.left - b.left + a.width / 2, y = a.top - b.top + a.height / 2;
      // An elliptical halo expands beyond the card into the background.
      bursts.push({ x, y, radius: a.width * .52, age: 0, life: 2.8, ring: true });
      for (let i = 0; i < 30; i++) {
        const angle = random(0, Math.PI * 2), speed = random(25, 80);
        bursts.push({ x: x + Math.cos(angle) * a.width * .45, y: y + Math.sin(angle) * a.height * .45,
          vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, age: 0, life: random(1.5, 3), size: random(.8, 2) });
      }
    };
    function draw(dt) {
      time += dt;
      ctx.clearRect(0, 0, width, height);
      pointer.x += (pointer.targetX - pointer.x) * Math.min(1, dt * 2);
      pointer.y += (pointer.targetY - pointer.y) * Math.min(1, dt * 2);
      const color = '240,206,139';
      for (const p of particles) {
        p.y -= p.speed * dt;
        if (p.y < -15) p.y = height + 15;
        const x = p.x + Math.sin(time * .25 + p.phase) * 22 + pointer.x * p.depth;
        const y = p.y + pointer.y * p.depth;
        const opacity = .3 + .3 * Math.sin(time * .85 + p.phase);
        ctx.fillStyle = `rgba(${color},${opacity})`;
        ctx.beginPath(); ctx.arc(x, y, p.size, 0, Math.PI * 2); ctx.fill();
        if (p.size > 1.3) {
          const glow = ctx.createRadialGradient(x, y, 0, x, y, p.size * 6);
          glow.addColorStop(0, `rgba(${color},${opacity * .3})`); glow.addColorStop(1, `rgba(${color},0)`);
          ctx.fillStyle = glow; ctx.fillRect(x - 10, y - 10, 20, 20);
          ctx.strokeStyle = `rgba(${color},${opacity * .6})`; ctx.lineWidth = .6;
          ctx.beginPath(); ctx.moveTo(x - 4, y); ctx.lineTo(x + 4, y);
          ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4); ctx.stroke();
        }
      }
      bursts = bursts.filter(p => p.age < p.life);
      for (const p of bursts) {
        p.age += dt;
        const progress = p.age / p.life, alpha = Math.max(0, 1 - progress);
        if (p.ring) {
          const radius = p.radius + (1 - Math.pow(1 - progress, 3)) * 110;
          ctx.strokeStyle = `rgba(${color},${alpha * .32})`; ctx.lineWidth = .8;
          ctx.beginPath(); ctx.ellipse(p.x, p.y, radius, radius * 1.4, 0, 0, Math.PI * 2); ctx.stroke();
          const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius * 1.8);
          glow.addColorStop(0, `rgba(${color},${alpha * .12})`);
          glow.addColorStop(1, `rgba(${color},0)`);
          ctx.fillStyle = glow; ctx.fillRect(p.x - radius * 2, p.y - radius * 2, radius * 4, radius * 4);
        } else {
          p.x += p.vx * dt; p.y += p.vy * dt; p.vx *= Math.exp(-dt * .7); p.vy -= dt * 5;
          ctx.fillStyle = `rgba(${color},${alpha * .85})`;
          ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2); ctx.fill();
        }
      }
    }
    const loop = createAnimationLoop(draw);
    function visibility() {
      root.current?.classList.toggle('is-paused', document.hidden);
      if (document.hidden || lost) loop.stop(); else loop.start();
    }
    const contextLost = event => { event.preventDefault(); lost = true; loop.stop(); };
    const contextRestored = () => { lost = false; resize(true); visibility(); };
    const observer = new ResizeObserver(() => resize());
    observer.observe(root.current);
    window.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerleave', leave);
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('pageshow', visibility);
    window.addEventListener('focus', visibility);
    el.addEventListener('contextlost', contextLost);
    el.addEventListener('contextrestored', contextRestored);
    resize(); visibility();
    return () => {
      loop.stop(); observer.disconnect(); emit.current = null;
      window.removeEventListener('pointermove', move);
      document.removeEventListener('pointerleave', leave);
      document.removeEventListener('visibilitychange', visibility);
      window.removeEventListener('pageshow', visibility);
      window.removeEventListener('focus', visibility);
      el.removeEventListener('contextlost', contextLost);
      el.removeEventListener('contextrestored', contextRestored);
      ctx.clearRect(0, 0, width, height);
    };
  }, [enabled]);

  const previous = useRef(revealed);
  useEffect(() => {
    if (revealed > previous.current) emit.current?.(revealed - 1);
    previous.current = revealed;
  }, [revealed]);

  return <div ref={root} className={`atmosphere ${enabled ? 'is-animated' : ''}`} aria-hidden="true">
    <div className="atmosphere-mist" />
    <div className="ambient-light ambient-light-one" />
    <div className="ambient-light ambient-light-two" />
    <div className="ambient-rays" />
    <div className="celestial-orbit celestial-orbit-one" />
    <div className="celestial-orbit celestial-orbit-two" />
    <canvas ref={canvas} className="ambient-dust" />
  </div>;
}

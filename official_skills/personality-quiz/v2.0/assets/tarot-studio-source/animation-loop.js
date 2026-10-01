// Independent of React renders and draw locks. A frame error cannot cancel the next frame.
export function createAnimationLoop(draw, requestFrame = callback => window.requestAnimationFrame(callback), cancelFrame = id => window.cancelAnimationFrame(id)) {
  let running = false, frame = null, last = null;
  const tick = now => {
    if (!running) return;
    const dt = last === null ? 0 : Math.max(0, Math.min((now - last) / 1000, .05));
    last = now;
    frame = requestFrame(tick);
    draw(dt);
  };
  return {
    start() {
      if (running) return;
      running = true; last = null; frame = requestFrame(tick);
    },
    stop() {
      running = false; last = null;
      if (frame !== null) cancelFrame(frame);
      frame = null;
    },
  };
}

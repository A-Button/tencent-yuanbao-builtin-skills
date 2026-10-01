import { gsap } from 'gsap';

export function animateDeck(element, { shuffle, motion, onStage, onComplete }) {
  const cards = [...element.querySelectorAll('.deck-card')].filter(card => card.offsetWidth);
  const mobile = window.matchMedia('(max-width:700px)').matches;
  const fan = card => Number(card.style.getPropertyValue('--i'));
  const center = card => element.clientWidth / 2 - card.offsetLeft - card.offsetWidth / 2;
  gsap.set(cards, { transition: 'none', translate: 'none' });
  const timeline = gsap.timeline({ onComplete: () => {
    gsap.set(cards, { clearProps: 'transform,opacity,transition,translate,zIndex' });
    onComplete();
  } });
  if (!motion) return timeline.to(cards, { opacity: 1, duration: .08 });
  if (shuffle) {
    timeline.call(() => onStage('gathering'))
      .to(cards, { x: (_, card) => center(card), y: i => i * -.65 + 14,
        rotation: 0, scale: .94, duration: .42, stagger: { each: .012, from: 'center' }, ease: 'power3.inOut' })
      .call(() => onStage('shuffling'));
    // Two small packets separate, then interleave in opposite orders.
    for (let pass = 0; pass < 2; pass++) {
      const direction = pass ? -1 : 1;
      timeline.to(cards, {
        x: (i, card) => center(card) + (i % 2 ? 1 : -1) * direction * (mobile ? 57 : 90),
        y: i => i % 2 ? -12 : 21,
        rotation: i => (i % 2 ? 1 : -1) * direction * 9,
        duration: .25, ease: 'power2.inOut',
      }).to(cards, {
        x: (_, card) => center(card), y: i => -i * .65 + 14, rotation: 0,
        duration: .28, stagger: { each: .013, from: pass ? 'end' : 'start' }, ease: 'power2.inOut',
      });
    }
  } else {
    gsap.set(cards, { x: (_, card) => center(card), y: 35, rotation: 0, scale: .94, opacity: 0 });
    timeline.to(cards, { opacity: 1, duration: .15 });
  }
  return timeline.call(() => onStage('spreading')).to(cards, {
    x: 0, y: (_, card) => fan(card) ** 2 * (mobile ? .5 : 1.1),
    rotation: (_, card) => fan(card) * (mobile ? 4 : 3.3), scale: 1, opacity: 1,
    duration: .65, stagger: { each: .022, from: 'center' }, ease: 'power3.out',
  });
}

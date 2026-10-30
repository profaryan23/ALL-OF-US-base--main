/* Inventory-only endless arc enhancement; keeps the existing variant/cart handlers. */
window.AllOfUsShopArc = function ({products, slots, select}) {
  const stage = document.getElementById('orbitStage');
  const categories = document.getElementById('arcCategories');
  const counter = document.getElementById('arcCounter');
  const motion = document.getElementById('arcMotion');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let indices = products.map((_, i) => i);
  let position = 0, target = 0, velocity = 0, last = 0, pauseUntil = 0;
  let active = -1, paused = reduced.matches, dragging = false, moved = false, startX = 0, previousX = 0, lastCounter = '';
  const colors = new Map();
  const wrap = (value, total) => ((value % total) + total) % total;
  const interrupt = () => { pauseUntil = performance.now() + 3200; };
  function choose(index) {
    if (active === index) return;
    active = index;
    select(index);
    const chosen = colors.get(index);
    if (chosen !== undefined) document.querySelectorAll('#detailSwatches button')[chosen]?.click();
    const panel = document.getElementById('productDetails');
    if (!reduced.matches) panel.animate([{opacity: .35, transform: 'translateY(12px)'}, {opacity: 1, transform: 'translateY(0)'}], {duration: 300});
  }
  function render() {
    const total = indices.length;
    const spacing = innerWidth < 640 ? 115 : innerWidth < 1024 ? 145 : 175;
    indices.forEach((index, i) => {
      let delta = wrap(i - position + total / 2, total) - total / 2;
      const distance = Math.abs(delta);
      const slot = slots[index];
      slot.style.transform = `translate(-50%, -50%) translate3d(${delta * spacing * Math.max(.5, 1 - distance * .08)}px, ${Math.pow(distance, 1.8) * 18}px, 0) rotate(${delta * 12}deg) scale(${Math.max(.6, 1.12 - distance * .14)})`;
      slot.style.zIndex = 100 - Math.round(distance * 10);
      slot.style.opacity = Math.max(0, 1 - distance * .22);
      slot.style.pointerEvents = distance < 3.5 ? 'auto' : 'none';
    });
    if (total) {
      const current = wrap(Math.round(position), total);
      const text = `${String(current + 1).padStart(2, '0')} / ${String(total).padStart(2, '0')} · Swipe or use arrow keys`;
      if (text !== lastCounter) { counter.textContent = text; lastCounter = text; }
      choose(indices[current]);
    }
  }
  function snap(step) { interrupt(); target = Math.round(target + step); if (reduced.matches) position = target; render(); }
  function filter(category) {
    interrupt(); position = target = velocity = 0; active = -1;
    indices = products.flatMap((p, i) => category === null || p.category === category ? [i] : []);
    slots.forEach((slot, index) => { slot.hidden = !indices.includes(index); });
    render();
  }
  [null, ...new Set(products.map(p => p.category))].forEach(category => {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = category || 'All products';
    button.setAttribute('aria-pressed', String(category === null));
    button.addEventListener('click', () => { categories.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === button))); filter(category); });
    categories.append(button);
  });
  slots.forEach((slot, index) => {
    const button = slot.querySelector('button');
    const price = document.createElement('span'); price.className = 'arc-card-price'; price.textContent = 'Rs ' + products[index].price.toLocaleString('en-US', {minimumFractionDigits: 2});
    slot.querySelector('.orbit-label').append(price);
    button.addEventListener('click', event => {
      event.stopImmediatePropagation();
      if (moved) return;
      interrupt();
      const offset = wrap(indices.indexOf(index) - target + indices.length / 2, indices.length) - indices.length / 2;
      target += offset;
      if (reduced.matches) position = target;
      render();
    }, true);
  });
  stage.tabIndex = 0; stage.setAttribute('role', 'region'); stage.setAttribute('aria-label', 'Revolving product collection. Use left and right arrow keys.');
  stage.addEventListener('keydown', event => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); snap(event.key === 'ArrowLeft' ? -1 : 1); } });
  stage.addEventListener('wheel', event => { event.preventDefault(); interrupt(); target += (Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY) * .003; }, {passive: false});
  stage.addEventListener('pointerdown', event => { if (event.button !== 0) return; interrupt(); dragging = true; moved = false; startX = previousX = event.clientX; });
  window.addEventListener('pointermove', event => { if (!dragging) return; interrupt(); moved ||= Math.abs(event.clientX - startX) > 8; target -= (event.clientX - previousX) / (innerWidth < 640 ? 115 : 175); position = target; previousX = event.clientX; render(); });
  window.addEventListener('pointerup', () => { if (!dragging) return; dragging = false; target = Math.round(target); interrupt(); });
  window.addEventListener('pointercancel', () => { dragging = false; target = Math.round(target); interrupt(); });
  stage.addEventListener('dragstart', event => event.preventDefault());
  const panel = document.getElementById('productDetails');
  panel.addEventListener('pointerdown', interrupt);
  panel.addEventListener('input', interrupt);
  panel.addEventListener('focusin', interrupt);
  document.getElementById('detailSwatches').addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    const index = [...button.parentNode.children].indexOf(button); colors.set(active, index);
    const image = slots[active].querySelector('img'); const variant = products[active].colors[index];
    image.src = variant.img || products[active].img; image.style.filter = variant.filter || 'none';
  });
  function updateMotion() { motion.textContent = paused ? 'Resume motion' : 'Pause motion'; motion.setAttribute('aria-pressed', String(paused)); }
  motion.addEventListener('click', () => { paused = !paused; interrupt(); updateMotion(); });
  reduced.addEventListener('change', () => { paused = reduced.matches; updateMotion(); });
  window.addEventListener('resize', render);
  function frame(now) {
    const dt = Math.min((now - (last || now)) / 1000, .032); last = now;
    const inspecting = panel.matches(':hover') || panel.contains(document.activeElement) || stage.contains(document.activeElement) || stage.matches(':hover');
    if (!paused && !dragging && !document.hidden && !inspecting && now > pauseUntil) target += dt * .12;
    if (reduced.matches) { position = target; velocity = 0; }
    else if (!dragging) { velocity += ((target - position) * 220 - velocity * 26) / .8 * dt; position += velocity * dt; }
    render(); requestAnimationFrame(frame);
  }
  updateMotion(); render(); requestAnimationFrame(frame);
};
/* Copy verified placements or generate a local PNG; no chart data is sent away. */
(() => {
  'use strict';
  const card = document.querySelector('.zodiac-panel');
  const copy = document.getElementById('zodiac-copy-result');
  const save = document.getElementById('zodiac-save-image');
  const copyDialog = document.getElementById('zodiac-copy-dialog');
  if (!card || !copy || !save || !copyDialog) return;

  const toastNode = document.getElementById('zodiac-toast');
  const copyFallback = document.getElementById('zodiac-copy-fallback');
  const selectCopy = document.getElementById('zodiac-select-copy');
  const closeCopy = document.getElementById('zodiac-close-copy');
  let posterPromise;
  let posterUrl;
  let toastTimer;
  let copyBusy = false;

  function toast(message) {
    clearTimeout(toastTimer);
    const openDialog = document.querySelector('dialog[open]');
    (openDialog || document.body).append(toastNode);
    toastNode.textContent = message;
    toastNode.hidden = false;
    toastTimer = setTimeout(() => { toastNode.hidden = true; }, 4200);
  }
  function openDialog(target) {
    if (typeof target.showModal === 'function') target.showModal();
    else {
      target.setAttribute('open', '');
      target.setAttribute('role', 'dialog');
      target.setAttribute('aria-modal', 'true');
    }
  }
  function closeDialog(target) {
    if (typeof target.close === 'function') target.close();
    else target.removeAttribute('open');
    document.body.append(toastNode);
  }
  function transferText() {
    const names = {sun: '太阳', ascendant: '上升', moon: '月亮', venus: '金星', mercury: '水星'};
    const stable = [];
    const uncertain = [];
    card.querySelectorAll('[data-zodiac-key]').forEach(node => {
      const key = node.getAttribute('data-zodiac-key');
      const body = names[key];
      if (!body) return;
      const signNode = node.querySelector('.zodiac-sign,.zodiac-fact-sign');
      const display = signNode ? signNode.textContent.trim() : '暂未确定';
      if (node.getAttribute('data-status') === 'available') stable.push({body, sign: display});
      else {
        const reasonNode = node.querySelector('.zodiac-status-note,.zodiac-fact-note');
        uncertain.push({body, display, reason: reasonNode ? reasonNode.textContent.trim() : '当前尚未确定'});
      }
    });
    return [
      '请根据以下已核验的西洋星盘位置做文化象征解读，优先说明相关配置之间的关系。待定项不要当成已确定位置，也不要从短标签推断宫位或相位。',
      'WESTERN_CHART_RESULT_V1',
      JSON.stringify({precision: card.getAttribute('data-precision'), stable_placements: stable, uncertain_placements: uncertain}, null, 2)
    ].join('\n');
  }
  function showPoster() {
    return globalThis.ResultImage.show({container:document.getElementById('zodiac-image-mount'),url:posterUrl,name:'星座排盘.png',title:'星盘图片',trigger:save});
  }
  function waitForImage(img) {
    if (img.complete) return img.naturalWidth ? Promise.resolve() : Promise.reject(new Error('图片未加载'));
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => finish(new Error('图片加载超时')), 8000);
      const loaded = () => finish();
      const failed = () => finish(new Error('图片未加载'));
      function finish(error) {
        clearTimeout(timer);
        img.removeEventListener('load', loaded);
        img.removeEventListener('error', failed);
        if (error) reject(error); else resolve();
      }
      img.addEventListener('load', loaded);
      img.addEventListener('error', failed);
    });
  }
  async function buildPoster() {
    if (typeof html2canvas !== 'function') throw new Error('图片组件不可用');
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    const host = document.createElement('div');
    host.className = 'zodiac-export-host';
    host.setAttribute('aria-hidden', 'true');
    const surface = document.createElement('div');
    surface.className = 'zodiac-export-surface';
    const clone = card.cloneNode(true);
    clone.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
    surface.append(clone);
    host.append(surface);
    document.body.append(host);
    try {
      await Promise.all([...clone.querySelectorAll('img')].map(waitForImage));
      const canvas = await html2canvas(surface, {
        scale: 2, backgroundColor: '#f5faf5', useCORS: false,
        allowTaint: false, logging: false, windowWidth: 1000,
        scrollX: 0, scrollY: 0, imageTimeout: 8000
      });
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      canvas.width = 1;
      canvas.height = 1;
      if (!blob) throw new Error('浏览器无法导出图片');
      posterUrl = URL.createObjectURL(blob);
      return blob;
    } finally {
      host.remove();
    }
  }
  async function ensurePoster() {
    if (!posterPromise) posterPromise = buildPoster().catch(error => { posterPromise = null; throw error; });
    return posterPromise;
  }
  async function run(button, action) {
    save.disabled = true;
    button.textContent = '正在生成…';
    clearTimeout(toastTimer);toastNode.hidden = true;
    try { await action(await ensurePoster()); }
    catch (error) { toast('图片生成失败，请重试。'); }
    finally {
      save.disabled = false;
      save.textContent = '保存或分享图片';
    }
  }
  save.addEventListener('click', () => run(save, async () => showPoster()));
  copy.addEventListener('click', async () => {
    if (copyBusy) return;
    copyBusy = true;
    copy.disabled = true;
    const text = transferText();
    copyFallback.value = text;
    let copied = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        copied = true;
      }
    } catch (error) { /* Try native selection below. */ }
    if (!copied) {
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.cssText = 'position:fixed;left:0;top:0;opacity:0;font-size:16px';
      document.body.append(area);
      area.select();
      area.setSelectionRange(0, text.length);
      try { copied = document.execCommand('copy') === true; }
      catch (error) { /* Use the visible fallback dialog. */ }
      area.remove();
      copy.focus({preventScroll: true});
    }
    if (copied) toast('已复制星盘结果，粘贴给元宝即可继续解读。');
    else {
      openDialog(copyDialog);
      copyFallback.focus();
      copyFallback.select();
      toast('浏览器未允许自动复制，请手动复制。');
    }
    copyBusy = false;
    copy.disabled = false;
  });
  selectCopy.addEventListener('click', () => {
    copyFallback.focus();
    copyFallback.select();
    copyFallback.setSelectionRange(0, copyFallback.value.length);
    toast('已选中，请使用系统复制。');
  });
  closeCopy.addEventListener('click', () => closeDialog(copyDialog));
  for (const modal of [copyDialog]) modal.addEventListener('close', () => document.body.append(toastNode));
})();

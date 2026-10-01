(function(root){
  'use strict';
  const entries=new WeakMap();let active=null;
  const isMobile=()=>/iPhone|iPad|iPod|Android/i.test(root.navigator.userAgent)||
    (root.navigator.platform==='MacIntel'&&root.navigator.maxTouchPoints>1);
  function clear(container){entries.get(container)?.close();}
  function show({container,url,name='结果图片.png',title='结果图片',dark=false,trigger=null}){
    if(!container||!container.isConnected)throw new Error('Missing image container');
    if(!/^(data:image\/png;base64,|blob:)/.test(url))throw new Error('Invalid local PNG');
    const current=entries.get(container);
    if(current?.url===url&&!current.failed)return current.ready;
    active?.close();
    const doc=root.document,body=doc.body,previous=trigger||doc.activeElement;
    const scrollX=root.scrollX,scrollY=root.scrollY,mobile=isMobile();
    const host=doc.createElement('div');host.dataset.resultImage='true';
    host.style.cssText='all:initial!important;position:fixed!important;display:block!important;inset:0!important;z-index:2147483646!important;isolation:isolate!important;';
    const shadow=host.attachShadow({mode:'open'});
    shadow.innerHTML=`<style>
      :host{color-scheme:${dark?'dark':'light'}}
      *{box-sizing:border-box}[hidden]{display:none!important}
      .overlay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:12px;background:#0009;font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:${dark?'#eadfc9':'#202820'}}
      .panel{display:flex;flex-direction:column;min-width:0;min-height:0;width:100%;max-width:680px;height:100%;max-height:900px;overflow:hidden;border-radius:20px;background:${dark?'#171a15':'#f8faf6'};border:1px solid ${dark?'#514a3d':'#dce5dc'}}
      header{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid ${dark?'#514a3d':'#dce5dc'}}
      h2{font:600 16px/1.4 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;margin:0;min-width:0}
      button{min-height:44px;border:0;border-radius:12px;padding:10px 16px;background:${dark?'#30342c':'#e8eee6'};color:inherit;font:600 14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;cursor:pointer;touch-action:manipulation}
      button:focus-visible,.preview:focus-visible{outline:3px solid #438cd2;outline-offset:-3px}button:disabled{opacity:.55;cursor:wait}
      .preview{flex:1 1 0;min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;touch-action:pan-y pinch-zoom;padding:12px;scrollbar-width:thin}
      img{display:block;width:100%;max-width:100%;height:auto;margin:0 auto;border-radius:8px;-webkit-touch-callout:default;user-select:auto;-webkit-user-select:auto}
      footer{flex:0 0 auto;padding:14px 16px;border-top:1px solid ${dark?'#514a3d':'#dce5dc'};text-align:center}
      .hint{font-size:14px;line-height:1.5;margin:0;color:${dark?'#d3c4aa':'#526353'}}
      .download{display:block;min-width:180px;margin:0 auto 8px;background:${dark?'#d9c09a':'#263d2b'};color:${dark?'#1a201a':'#fff'}}
      .status{font-size:13px;line-height:1.6;margin:12px 0}
      @supports(padding:max(0px)){.overlay{padding:max(12px,env(safe-area-inset-top)) max(12px,env(safe-area-inset-right)) max(12px,env(safe-area-inset-bottom)) max(12px,env(safe-area-inset-left))}}
      @media(max-height:420px){.overlay{padding:6px}header,footer{padding:6px 12px}.preview{padding:6px}.hint{font-size:12px}}
    </style><div class="overlay"><section class="panel" role="dialog" aria-modal="true" aria-labelledby="image-title"><header><h2 id="image-title"></h2><button type="button" class="close" aria-label="关闭图片预览">关闭</button></header><div class="preview" tabindex="0" role="region" aria-label="结果图片，可滚动查看"><p class="status" role="status">正在加载图片…</p><img hidden draggable="false"></div><footer><button type="button" class="download" hidden disabled>下载图片</button><p class="hint"></p></footer></section></div>`;
    const get=s=>shadow.querySelector(s),image=get('img'),status=get('.status'),download=get('.download');
    get('h2').textContent=title;image.alt=title;
    get('.hint').textContent=mobile?'长按图片保存或分享':'下载图片后即可分享，也可右键保存图片';
    download.hidden=mobile;
    const styles={};for(const key of ['position','top','left','width','overflow'])styles[key]=body.style[key];
    const background=[...body.children].map(el=>[el,el.inert,el.getAttribute('aria-hidden')]);
    background.forEach(([el])=>{el.inert=true;el.setAttribute('aria-hidden','true');});
    body.style.position='fixed';body.style.top=`${-scrollY}px`;body.style.left=`${-scrollX}px`;body.style.width='100%';body.style.overflow='hidden';body.append(host);
    const vv=root.visualViewport;
    function resize(){
      host.style.setProperty('width',`${vv?.width||doc.documentElement.clientWidth}px`,'important');
      host.style.setProperty('height',`${vv?.height||root.innerHeight}px`,'important');
      host.style.setProperty('top',`${vv?.offsetTop||0}px`,'important');host.style.setProperty('left',`${vv?.offsetLeft||0}px`,'important');
    }
    resize();root.addEventListener('resize',resize);vv?.addEventListener('resize',resize);vv?.addEventListener('scroll',resize);
    let settled=false,closed=false,resolveReady,rejectReady;
    const ready=new Promise((resolve,reject)=>{resolveReady=resolve;rejectReady=reject;});
    function close(){
      if(closed)return;closed=true;if(!settled){settled=true;resolveReady(null);}
      host.remove();root.removeEventListener('resize',resize);vv?.removeEventListener('resize',resize);vv?.removeEventListener('scroll',resize);
      for(const [key,value]of Object.entries(styles))body.style[key]=value;
      background.forEach(([el,inert,aria])=>{if(el.isConnected){el.inert=inert;if(aria===null)el.removeAttribute('aria-hidden');else el.setAttribute('aria-hidden',aria);}});
      root.scrollTo({left:scrollX,top:scrollY,behavior:'instant'});previous?.focus?.({preventScroll:true});
      entries.delete(container);if(active===entry)active=null;
    }
    const entry={url,host,ready,close};entries.set(container,entry);active=entry;
    get('.close').addEventListener('click',close);
    shadow.addEventListener('keydown',event=>{
      if(event.key==='Escape'){event.preventDefault();close();}
      if(event.key==='Tab'){
        const items=[get('.close'),get('.preview'),download].filter(el=>!el.hidden&&!el.disabled);
        const index=items.indexOf(shadow.activeElement),next=(index+(event.shiftKey?-1:1)+items.length)%items.length;
        event.preventDefault();items[next].focus({preventScroll:true});
      }
    });
    download.addEventListener('click',()=>{
      const link=doc.createElement('a');link.href=url;link.download=name;link.target='_blank';link.rel='noopener';body.append(link);link.click();link.remove();
    });
    image.onload=()=>{if(settled||closed)return;settled=true;image.hidden=false;status.hidden=true;download.disabled=false;resolveReady(host);};
    image.onerror=()=>{if(settled||closed)return;settled=true;entry.failed=true;status.textContent='图片加载失败，请关闭后重试。';rejectReady(new Error('Image load failed'));};
    // Keep the image's native context menu. Saving/sharing on mobile requires a real long press.
    image.src=url;get('.close').focus({preventScroll:true});return ready;
  }
  root.ResultImage=Object.freeze({show,clear});
})(globalThis);

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { TarotWheel } from './TarotWheel';
import { assetUrl, cardArt, createDeck, orientationLabel } from './tarot-data';
import { formatHandoff, copyHandoff } from './handoff';
import '../result-image.js';
import { clearLocalState, makeShareSnapshot, readLocalState, readShareFragment, readShareSnapshot, saveLocalState } from './artifact-state';
import { Atmosphere } from './Atmosphere';
import { renderSharePoster } from './share-poster';
import { useViewportLayout } from './use-viewport-layout';
import { ArrowRight, ArrowCounterClockwise, X, Check, Shuffle } from '@phosphor-icons/react';
// Fonts and artwork are embedded by the single-file packager.
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const config = (() => {
  try { return JSON.parse(document.getElementById('tarot-standalone-config')?.textContent || '{}'); }
  catch { return {}; }
})();
const question = config.question || '';
const artifactId = config.artifactId || '';

function Card({ card, faceUp=true, motion=true, disabled=false, onClick }) {
  const outer=useRef(null), tilt=useRef(null);
  const move=e=>{
    if(!motion||disabled||e.pointerType==='touch'||reducedMotion()) return;
    const r=outer.current.getBoundingClientRect(), x=(e.clientX-r.left)/r.width-.5, y=(e.clientY-r.top)/r.height-.5;
    gsap.to(tilt.current,{rotateY:x*13,rotateX:-y*11,duration:.45,overwrite:true});
    outer.current.style.setProperty('--glare-x',`${(x+.5)*100}%`); outer.current.style.setProperty('--glare-y',`${(y+.5)*100}%`);
  };
  return <button ref={outer} className="tarot-card" disabled={disabled} onPointerMove={move} onPointerLeave={()=>gsap.to(tilt.current,{rotateX:0,rotateY:0,duration:motion?.7:0})} onClick={onClick} aria-label={`查看${card.title}的解读`}>
    <span className="card-table-shadow"/><span ref={tilt} className="card-tilt"><span className={`card-flipper ${faceUp?'face-up':''}`}>
      <span className="card-side card-back"><img src={assetUrl('dark-back.jpg')} alt="" draggable="false"/></span>
      <span className="card-side card-front"><img className={card.reversed?'art-reversed':''} src={cardArt(card)} alt={`${card.title} · ${orientationLabel(card)}`} draggable="false"/><span className="foil"/></span>
    <span className="card-edge"/></span></span>
  </button>;
}
function Modal({children,label,onClose,className='',showClose=true}) {
  const ref=useRef(null);
  useEffect(()=>{const el=ref.current,previous=document.activeElement;el.showModal();const field=el.querySelector('textarea');if(field){field.focus();field.select();}const cancel=e=>{e.preventDefault();onClose();};el.addEventListener('cancel',cancel);document.body.style.overflow='hidden';return()=>{el.removeEventListener('cancel',cancel);el.close();document.body.style.overflow='';previous?.focus();};},[]);
  return <dialog ref={ref} aria-label={label} className={`modal ${className}`} onClick={e=>{if(e.target===e.currentTarget)onClose();}}>{showClose&&<button className="close-button" aria-label="关闭" onClick={onClose}><X size={22} weight="light"/></button>}{children}</dialog>;
}
export function App() {
  const initial=useRef(null),openedFromShare=useRef(false);
  if(!initial.current){
    const shared=readShareFragment(artifactId);
    openedFromShare.current=Boolean(shared);
    initial.current=shared||readLocalState(artifactId)||{deck:createDeck(),used:[],selected:[],revealed:[]};
  }
  const [selected,setSelected]=useState(initial.current.selected),[revealed,setRevealed]=useState(initial.current.revealed),[used,setUsed]=useState(initial.current.used),[busy,setBusy]=useState(false),[detail,setDetail]=useState(null),[exporting,setExporting]=useState(false),[image,setImage]=useState(''),[notice,setNotice]=useState(''),[motion,setMotion]=useState(!reducedMotion());
  const [manualCopy,setManualCopy]=useState('');
  const [copying,setCopying]=useState(false);
  const copyLock=useRef(false),copyField=useRef(null),posterMount=useRef(null),posterEpoch=useRef(0);
  const appRoot=useRef(null);
  const [showQuestion,setShowQuestion]=useState(false);
  const layout=useViewportLayout(busy,Boolean(question));
  const geometry=React.useMemo(()=>({width:layout.wheelWidth,wheel:layout.wheel}),[layout.wheelWidth,layout.wheel]);
  const scene=useRef(null),deck=useRef(null),pool=useRef(null),lock=useRef(false),activeTimeline=useRef(null);
  if(!pool.current)pool.current=initial.current.deck;
  const total=3;
  const [round,setRound]=useState(0),[phase,setPhase]=useState('idle'),[activeSlot,setActiveSlot]=useState(null);
  const pendingDraw=useRef(null);
  const complete=selected.length===total&&revealed.length===total&&(!busy||phase==='gathering');
  useEffect(()=>{document.documentElement.dataset.theme='dark';document.title='观照 · 塔罗抽牌';},[]);
  useEffect(()=>{
    if(!busy&&!openedFromShare.current)saveLocalState(artifactId,pool.current,used);
  },[busy,used]);
  useEffect(()=>{
    if(window.parent===window)return;
    const onMessage=event=>{
      if(event.source!==window.parent||!event.data||typeof event.data!=='object')return;
      const {type,requestId}=event.data;
      if(type==='tarot:request-share-snapshot'&&typeof requestId==='string'&&requestId.length<=128){
        event.source.postMessage({type:'tarot:share-snapshot',requestId,
          snapshot:complete?makeShareSnapshot(artifactId,selected):null},event.origin==='null'?'*':event.origin);
      }
      if(type==='tarot:open-share-snapshot'){
        const shared=readShareSnapshot(event.data.snapshot,artifactId);
        if(!shared)return;
        activeTimeline.current?.kill();deck.current?.stop();lock.current=false;
        openedFromShare.current=true;pool.current=shared.deck;
        pendingDraw.current=null;gsap.set(scene.current,{clearProps:'opacity'});
        setImage('');posterEpoch.current++;globalThis.ResultImage.clear(posterMount.current);setDetail(null);setManualCopy('');
        setSelected(shared.selected);setRevealed(shared.revealed);setUsed([]);
        setBusy(false);setPhase('idle');setActiveSlot(null);
      }
    };
    window.addEventListener('message',onMessage);
    return()=>window.removeEventListener('message',onMessage);
  },[selected,complete]);
  useEffect(()=>{const query=window.matchMedia('(prefers-reduced-motion: reduce)');const change=()=>{setMotion(!query.matches);if(query.matches)activeTimeline.current?.timeScale(100);};query.addEventListener('change',change);return()=>query.removeEventListener('change',change);},[]);
  useEffect(()=>{pool.current.forEach(c=>{const img=new Image();img.src=cardArt(c);});},[round]);
  useEffect(()=>{if(!notice)return;const id=setTimeout(()=>setNotice(''),4500);return()=>clearTimeout(id);},[notice]);
  useEffect(()=>()=>{activeTimeline.current?.kill();},[]);
  useLayoutEffect(()=>{
    if(!round)return;
    // The old content stays transparent until React commits the new round.
    if(motion&&!reducedMotion()){
      activeTimeline.current=gsap.to(scene.current,{opacity:1,duration:.24,ease:'power1.out',onComplete:()=>gsap.set(scene.current,{clearProps:'opacity'})});
    }else gsap.set(scene.current,{clearProps:'opacity'});
  },[round]);
  useLayoutEffect(()=>{
    const pending=pendingDraw.current;
    if(!pending)return;
    pendingDraw.current=null;
    const {slot,origin,width,height,angle,keyboard}=pending;
    const target=scene.current.querySelector(`[data-slot="${slot}"] .tarot-card`);
    const flipper=target.querySelector('.card-flipper'),shadow=target.querySelector('.card-table-shadow');
    const rect=target.getBoundingClientRect();
    const dx=origin.left+origin.width/2-rect.left-rect.width/2;
    const dy=origin.top+origin.height/2-rect.top-rect.height/2;
    const sx=width/rect.width,sy=height/rect.height,side=dx<0?-1:1;
    const animate=motion&&!reducedMotion();
    const travel={t:0};
    function paint(){
      const t=travel.t,u=1-t;
      // One continuous curved gesture: a small radial lift, then a soft arrival.
      const x=u*u*u*dx+3*u*u*t*(dx+side*24)+3*u*t*t*(side*25);
      const y=u*u*u*dy+3*u*u*t*(dy-65)+3*u*t*t*(-30);
      const swell=Math.sin(t*Math.PI)*.025;
      target.style.transform=`translate3d(${x}px,${y}px,0) rotate(${angle*(1-t)-side*4*Math.sin(t*Math.PI)}deg) scale(${sx+(1-sx)*t+swell},${sy+(1-sy)*t+swell})`;
    }
    gsap.set(flipper,{transition:'none',rotationY:0});
    target.dataset.flip='travel';paint();
    const duration=t=>animate?t:.01;
    activeTimeline.current=gsap.timeline({onComplete:()=>{
      target.style.transform='';delete target.dataset.flip;
      gsap.set([flipper,shadow],{clearProps:'transform,transition,opacity'});
      lock.current=false;setBusy(false);setPhase('idle');setActiveSlot(null);
      if(keyboard)requestAnimationFrame(()=>{
        if(slot===total-1)scene.current.querySelector('.completion .primary')?.focus({preventScroll:true});
        else deck.current?.focusNext();
      });
    }})
      .to(travel,{t:1,duration:duration(.78),ease:'power2.inOut',onUpdate:paint},0)
      .to(shadow,{opacity:.55,scale:1.15,duration:duration(.3)},0)
      .call(()=>{setPhase('revealing');target.dataset.flip='edge';},[],duration(.46))
      .to(flipper,{rotationY:90,scale:1.02,duration:duration(.3),ease:'power2.in'},duration(.46))
      .call(()=>{setRevealed(v=>[...v,slot]);target.dataset.flip='open';},[],duration(.84))
      .to(flipper,{rotationY:180,scale:1,duration:duration(.46),ease:'power2.out'},duration(.84))
      .to(shadow,{opacity:0,scale:.8,duration:duration(.44)},duration(.84))
      .to({}, {duration:duration(.08)});
    if(slot===total-1&&deck.current?.element)activeTimeline.current.to(deck.current.element,{opacity:0,y:22,duration:duration(.2)},'-=.12');
  },[selected.length]);
  function draw(index,event){
    if(lock.current||selected.length>=total||used.includes(index))return;
    const source=event.currentTarget;
    deck.current?.stop();
    const origin=source.getBoundingClientRect();
    pendingDraw.current={slot:selected.length,origin,width:source.offsetWidth,height:source.offsetHeight,angle:Number(source.dataset.angle||0),keyboard:event.detail===0};
    lock.current=true;setBusy(true);setPhase('lifting');setActiveSlot(selected.length);
    saveLocalState(artifactId,pool.current,[...used,index]);
    setUsed(v=>[...v,index]);setSelected(v=>[...v,pool.current[index]]);
  }
  function reset(){
    if(lock.current||exporting||copyLock.current)return;
    openedFromShare.current=false;
    clearLocalState(artifactId);
    deck.current?.stop();
    lock.current=true;setBusy(true);setPhase('gathering');setActiveSlot(null);
    const restart=()=>{setSelected([]);setRevealed([]);setUsed([]);setImage('');setManualCopy('');posterEpoch.current++;globalThis.ResultImage.clear(posterMount.current);setRound(v=>v+1);pool.current=createDeck();};
    if(selected.length&&motion&&!reducedMotion()){
      // Fade the complete table once; do not briefly restore old cards before unmount.
      activeTimeline.current=gsap.timeline({onComplete:restart})
        .to(scene.current,{opacity:0,duration:.22,ease:'power1.inOut'});
    }else restart();
  }
  async function generatePoster(){if(image)return image;const epoch=posterEpoch.current;setExporting(true);try{const data=await renderSharePoster(selected,cardArt,orientationLabel);if(epoch!==posterEpoch.current)return null;setImage(data);return data;}catch(e){console.error('Poster export failed',e);setNotice('图片生成遇到问题，请稍后重试。');return null;}finally{setExporting(false);}}
  async function openShare(event){if(exporting||copyLock.current)return;const trigger=event.currentTarget;const data=await generatePoster();if(data)try{await globalThis.ResultImage.show({container:posterMount.current,url:data,name:'观照-我的三张牌.png',title:'塔罗结果图片',dark:true,trigger});}catch{setNotice('图片加载失败，请重试。');}}
  async function handoff(){
    if(copyLock.current)return;
    copyLock.current=true;setCopying(true);
    const text=formatHandoff(question,null,selected);
    try{
      if(await copyHandoff(text)){setManualCopy('');setNotice('已复制结果，粘贴回对话即可继续解读。');}
      else{setManualCopy(text);setNotice('浏览器未允许自动复制，请手动复制。');}
    }finally{copyLock.current=false;setCopying(false);}
  }
  function selectCopy(){copyField.current?.focus();copyField.current?.select();setNotice('已选中，请使用系统复制。');}
  return <div ref={appRoot} style={{'--table-width':`${layout.width}px`,'--table-height':`${layout.height}px`,'--table-header':`${layout.header}px`,'--table-intro':`${layout.intro}px`,'--table-slot':`${layout.slot}px`,'--table-leading':`${layout.leading}px`,'--wheel-width':`${layout.wheelWidth}px`,'--lower-height':`${layout.wheel.height+52}px`,'--safe-top':`${layout.insets.top}px`,'--safe-right':`${layout.insets.right}px`,'--safe-bottom':`${layout.insets.bottom}px`,'--safe-left':`${layout.insets.left}px`}} className={`app dark viewport-layout ${layout.landscape?'landscape-table':''} ${complete?'is-complete':''} ${!motion?'reduce-motion':''} phase-${phase}`}>
    <img className="scene-background" src={assetUrl('dark-background.jpg')} alt=""/>
    <Atmosphere enabled={motion} revealed={revealed.length}/>
    <header className="topbar"><div className="brand"><span>观照</span><small>TAROT<br/>JOURNAL</small></div>{complete&&<button className="reset text-button" onClick={reset} disabled={busy||exporting} aria-disabled={busy||exporting||copying}><span>再抽一次</span><ArrowCounterClockwise size={19} weight="light"/></button>}</header>
    <main ref={scene} className="experience" aria-busy={busy}>
      <section className="introduction"><h1>{complete?'答案，在你心中回响。':'请在心中默念你的问题'}</h1><p className={`result-guidance ${complete?'':'is-placeholder'}`} aria-hidden={!complete}>听见此刻的感受，让答案慢慢清晰。</p>{question&&<button className="question-context" onClick={()=>setShowQuestion(true)} aria-label={`查看完整问题：${question}`}>{question}</button>}</section>
      <section className="spread" aria-label="你的三张牌">{Array.from({length:total},(_,i)=><div key={i} className={`slot ${selected[i]?'has-card':''} ${activeSlot===i?'is-receiving':''} ${!busy&&i===selected.length?'is-next':''}`} data-slot={i}><div className="slot-face">{selected[i]?<Card motion={motion} disabled={busy} card={selected[i]} faceUp={revealed.includes(i)} onClick={()=>!busy&&setDetail(i)}/>:<div className="empty-card"><img src={assetUrl('dark-back.jpg')} alt=""/></div>}</div><div className="card-caption">{selected[i]&&revealed.includes(i)&&<button onClick={()=>!busy&&setDetail(i)}>{selected[i].title}<em className="orientation">{orientationLabel(selected[i])}</em></button>}</div></div>)}</section>
      <div className={`lower-stage ${complete?'result-stage':'draw-stage'}`}>
      {complete&&<section className="card-readings" aria-label="牌面解读">{selected.map(card=><article className="reading-summary" key={card.id} aria-label={`${card.title} · ${orientationLabel(card)}`}><h2 className="reading-summary-title">{card.title}<span>{orientationLabel(card)}</span></h2><p className="card-reading">{card.text}</p></article>)}</section>}
      {!complete?<section key="drawing" className="draw-area" aria-label="抽牌区"><TarotWheel geometry={geometry} ref={deck} theme="dark" round={round} motion={motion} busy={busy} used={used} onPick={draw} onBegin={stage=>{lock.current=true;setBusy(true);setPhase(stage);}} onStage={setPhase} onReady={()=>{lock.current=false;setBusy(false);setPhase('idle');}}/>
        <span className="sr-only" role="status">{busy?'动画进行中':'可以继续选牌'}</span><button className="shuffle text-button" onClick={reset} disabled={busy||exporting}><Shuffle size={16} weight="light"/>重新洗牌</button></section>:<section key="completed" className="completion"><div className="completion-actions"><button className="result-button secondary" disabled={exporting} aria-disabled={copying||exporting} aria-busy={copying} onClick={handoff}>复制给元宝</button><button className="result-button primary" disabled={exporting} aria-disabled={exporting||copying} onClick={openShare}>{exporting?'正在生成…':'分享结果图片'}</button></div><div ref={posterMount}/></section>}
      </div>
    </main>
    {showQuestion&&<Modal label="你的问题" onClose={()=>setShowQuestion(false)} className="utility-modal question-modal"><h2>你的问题</h2><p>{question}</p></Modal>}
    {detail!==null&&<Modal label={selected[detail].title} onClose={()=>setDetail(null)} className="reading-modal"><img className="reading-art" src={cardArt(selected[detail])} style={{transform:selected[detail].reversed?'rotate(180deg)':undefined}} alt={selected[detail].title}/><div className="reading-copy"><p className="eyebrow">{orientationLabel(selected[detail])} · {selected[detail].arcanaLabel}</p><h2>{selected[detail].title}</h2><p className="reading-keywords">{selected[detail].keywords.join(' / ')}</p><p>{selected[detail].text}</p><button className="text-button" onClick={()=>setDetail(null)}>返回<ArrowRight size={19}/></button></div></Modal>}
    {manualCopy&&<Modal label="手动复制结果" onClose={()=>setManualCopy('')} className="utility-modal copy-modal" showClose={false}><h2>手动复制结果</h2><p>以下是复制回对话的完整内容。请选中文本后使用系统复制。</p><textarea ref={copyField} readOnly value={manualCopy} aria-label="完整塔罗结果" onFocus={event=>event.currentTarget.select()}/><div className="dialog-actions"><button className="result-button secondary" onClick={()=>setManualCopy('')}>关闭</button><button className="result-button primary" onClick={selectCopy}>全选内容</button></div></Modal>}
    {notice&&<div className="toast" role="status"><Check size={18}/>{notice}</div>}
  </div>;
}

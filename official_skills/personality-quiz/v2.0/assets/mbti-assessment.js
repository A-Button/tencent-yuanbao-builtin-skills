(function(){
'use strict';
// Navigation is independent of the DOM so review and repagination can be verified.
class QuizFlow {
  constructor(total){this.total=total;this.answers=new Map();this.pages=[[0,total]];this.page=0;this.active=0;this.reviewing=false;}
  range(){return this.pages[this.page];}
  locate(index){return this.pages.findIndex(([start,end])=>index>=start&&index<end);}
  visit(index,review=true){this.active=Math.max(0,Math.min(this.total-1,index));this.page=this.locate(this.active);this.reviewing=review;}
  repaginate(heights,budget){
    const pages=[];let start=0,used=0;
    heights.forEach((height,index)=>{if(index>start&&used+height>budget){pages.push([start,index]);start=index;used=0;}used+=height;});
    pages.push([start,this.total]);this.pages=pages;this.page=this.locate(this.active);
  }
  select(index,value,advance=true){
    if(this.answers.has(index+1)||!advance)this.reviewing=true;
    this.active=index;this.answers.set(index+1,value);
    return this.reviewing?null:this.next();
  }
  next(){for(let index=0;index<this.total;index++)if(!this.answers.has(index+1))return index;return 'report';}
  resume(){this.reviewing=false;return this.next();}
}
if(typeof module==='object'&&module.exports)module.exports={QuizFlow};
if(typeof document==='undefined')return;
const DATA=JSON.parse(document.getElementById('assessment-data').textContent);
const Scoring=globalThis.PersonalityScoringV1;
const Report=globalThis.MbtiReport;
const Persist=globalThis.MbtiStateV1;
const $=id=>document.getElementById(id);
const restored=Persist.read(DATA);
const state=Object.assign(new QuizFlow(DATA.items.length),{timer:null,evaluation:null,report:null,posterUrl:null,posterBusy:false,copyBusy:false,toastTimer:null});
if(restored){state.answers=restored.answers;state.active=restored.active;state.reviewing=restored.reviewing;}
function persist(screen='question',active=state.active){Persist.write(DATA,state,screen,active);}
let layoutTimer=null,programmaticFocus=false;
const optionCaptions=['不认同','较不认同','不确定','较认同','认同'];
const reduceMotion=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const node=(tag,className,text)=>{const e=document.createElement(tag);if(className)e.className=className;if(text!==undefined)e.textContent=text;return e;};
const image=(src,alt,className)=>{const e=node('img',className);e.alt=alt;e.decoding='async';e.addEventListener('error',()=>{e.hidden=true;if(e.classList.contains('hero-image'))e.parentElement?.classList.add('text-only');if(e.parentElement?.classList.contains('illustration-slot'))e.parentElement.hidden=true;});e.src=src;return e;};
const pageItems=()=>DATA.items.slice(...state.range());
function toast(text){clearTimeout(state.toastTimer);$('toast').textContent=text;$('toast').hidden=false;state.toastTimer=setTimeout(()=>$('toast').hidden=true,4200);}
function cancelAdvance(){clearTimeout(state.timer);state.timer=null;}
function progress(){
  const count=state.answers.size,total=DATA.item_count,pct=Math.round(count/total*100);
  $('answerCount').textContent=`已答 ${count} / ${total} 题`;
  $('progressBar').style.width=pct+'%';
  document.querySelector('.progress-track').setAttribute('aria-valuenow',String(pct));
  document.querySelector('.progress-track').setAttribute('aria-valuetext',`已答 ${count} 题，共 ${total} 题`);
  $('previousPage').hidden=state.page===0;
  $('resumeQuiz').hidden=!state.reviewing;
  $('resumeQuiz').textContent=count===total?(state.report?'返回报告':'查看更新后的报告'):'继续答题';
}
function syncQuestions(){
  pageItems().forEach((item)=>{
    const row=$('question-'+item.id),answer=state.answers.get(item.id);
    row.classList.toggle('active',item.id-1===state.active);
    row.dataset.state=answer?'answered':'pending';
    row.querySelectorAll('.option').forEach((button,index)=>{
      const selected=Number(button.dataset.value)===answer;
      button.setAttribute('aria-checked',String(selected));
      button.tabIndex=selected||(!answer&&index===0)?0:-1;
    });
  });
  progress();
}
function focusQuestion(index){
  state.active=index;syncQuestions();
  persist();
  const heading=$('heading-'+(index+1));
  if(heading){programmaticFocus=true;heading.focus({preventScroll:true});programmaticFocus=false;}
}
function advanceTo(target){
  if(target==='report'){renderResult();return;}
  const page=state.locate(target);
  if(page!==state.page)showQuestions(page,target,false);else focusQuestion(target);
}
function choose(item,value,button,advance=true){
  cancelAdvance();
  const changed=state.answers.get(item.id)!==value;
  const target=state.select(item.id-1,value,advance);
  if(changed){state.evaluation=null;state.report=null;clearPoster();}
  persist('question',typeof target==='number'?target:state.active);
  syncQuestions();
  button.classList.remove('just-selected');void button.offsetWidth;button.classList.add('just-selected');
  if(target===null)return;
  const page=state.page;
  state.timer=setTimeout(()=>{
    state.timer=null;
    if(page!==state.page||state.reviewing||$('questionScreen').hidden)return;
    advanceTo(target);
  },reduceMotion()?0:target==='report'||state.locate(target)!==page?360:230);
}
function createQuestion(item){
    const row=node('div','question');row.id='question-'+item.id;
    const heading=node('h2','question-heading');heading.id='heading-'+item.id;heading.tabIndex=-1;
    heading.append(node('span','q-number',String(item.id).padStart(2,'0')),node('span','',item.text));
    const scale=node('div','scale');scale.setAttribute('role','radiogroup');scale.setAttribute('aria-labelledby',heading.id);
    [1,2,3,4,5].forEach((value,position)=>{
      const button=node('button','option');button.type='button';button.dataset.value=String(value);button.dataset.position=String(position+1);button.setAttribute('role','radio');
      button.setAttribute('aria-label',DATA.response_scale[String(value)]);button.title=DATA.response_scale[String(value)];
      const disc=node('span','option-disc');disc.append(image(DATA.icons.check,'',''));
      const caption=node('span','option-caption',optionCaptions[position]);caption.setAttribute('aria-hidden','true');
      button.append(disc,caption);button.addEventListener('click',()=>choose(item,value,button));
      button.addEventListener('keydown',event=>{
        if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
        event.preventDefault();cancelAdvance();
        const buttons=[...scale.querySelectorAll('.option')];
        const next=event.key==='Home'?0:event.key==='End'?4:(position+(['ArrowLeft','ArrowUp'].includes(event.key)?4:1))%5;
        buttons[next].focus();choose(item,Number(buttons[next].dataset.value),buttons[next],false);
      });
      scale.append(button);
    });
    row.append(heading,scale);
    function activate(){
      if(state.active!==item.id-1||state.answers.has(item.id)){
        cancelAdvance();
        if(state.answers.has(item.id)||item.id-1<state.active)state.reviewing=true;
        state.active=item.id-1;syncQuestions();
        persist();
      }
    }
    row.addEventListener('pointerdown',activate);
    row.addEventListener('focusin',()=>{if(!programmaticFocus)activate();});
    return row;
}
function renderPage(focus=true){
  cancelAdvance();$('questions').replaceChildren(...pageItems().map(createQuestion));
  syncQuestions();if(focus)focusQuestion(state.active);
}
function layoutQuestions(){
  if($('questionScreen').hidden)return;
  const keepFocus=$('questions').contains(document.activeElement);
  // Resizing cancels a pending jump; keep the selected question and expose resume.
  if(state.timer){state.reviewing=true;cancelAdvance();}
  document.body.classList.remove('quiz-needs-scroll');
  document.body.style.setProperty('--quiz-viewport-height',`${window.visualViewport?.height||innerHeight}px`);
  const card=document.querySelector('.quiz-card'),questions=$('questions');
  const measure=node('div','quiz-measure');measure.setAttribute('aria-hidden','true');measure.inert=true;
  measure.style.width=questions.getBoundingClientRect().width+'px';
  DATA.items.forEach(item=>{const row=createQuestion(item);row.classList.add('active');row.removeAttribute('id');row.querySelectorAll('[id]').forEach(e=>e.removeAttribute('id'));measure.append(row);});
  document.body.append(measure);
  const heights=[...measure.children].map(row=>Math.ceil(row.getBoundingClientRect().height)+1);
  const style=getComputedStyle(card);
  const budget=card.clientHeight-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom)-document.querySelector('.quiz-header').getBoundingClientRect().height-2;
  measure.remove();
  state.repaginate(heights,Math.max(1,budget));
  // Keep access to oversized text at exceptional zoom/viewport sizes.
  document.body.classList.toggle('quiz-needs-scroll',Math.max(...heights)>budget);
  renderPage(false);if(keepFocus)focusQuestion(state.active);
  if(state.reviewing)persist();
}
function showQuestions(page=state.page,active,review=true){
  cancelAdvance();state.page=Math.max(0,Math.min(state.pages.length-1,page));
  state.active=active===undefined?state.range()[0]:active;state.reviewing=review;
  $('resultScreen').hidden=true;$('questionScreen').hidden=false;document.body.classList.add('quiz-mode');
  renderPage(false);layoutQuestions();focusQuestion(state.active);window.scrollTo({top:0,behavior:'auto'});
}
function clearPoster(){globalThis.ResultImage.clear($('reportImageMount'));if(state.posterUrl){URL.revokeObjectURL(state.posterUrl);state.posterUrl=null;}}
function body(text){
  const p=node('p','body-copy');
  const phrases=['共同目标','整体意义','具体事实','对人的影响','逻辑、成本和现实限制','人与意义','明确边界','需要倾听、讨论还是具体协助','支持别人还是替别人承担'];
  const regex=new RegExp('('+phrases.join('|')+')','g');
  String(text).split(regex).forEach(part=>p.append(phrases.includes(part)?node('strong','',part):document.createTextNode(part)));
  return p;
}
function title(text,level='h3'){const h=node(level);h.append(node('span','underlined',text));return h;}
function illustration(slot){const wrapper=node('div','illustration-slot');const asset=DATA.illustrations[slot];if(asset)wrapper.append(image(asset.src,'',''));return wrapper;}
function contentPanel(key,profile,art){const panel=node('section','panel'+(art?' illustrated':''));panel.append(title(Report.SECTION_TITLES[key]),body(profile[key]));if(art)panel.append(illustration(key));return panel;}
function axesPanel(report){
  const section=node('section','panel axes-panel');section.append(node('h2','','MBTI 倾向'));
  const grid=node('div','axes-grid');
  report.axes.forEach(axis=>{
    const cell=node('section','axis');
    const h=title(`${axis.title}：${axis.displayLetter}`);
    if(axis.weak)h.append(node('span','weak-label','两侧接近'));
    const labels=node('div','axis-labels');labels.append(node('span','',`${axis.left} · ${axis.names[axis.left]} · ${axis.leftPct}%`),node('span','',`${axis.right} · ${axis.names[axis.right]} · ${axis.rightPct}%`));
    const track=node('div','axis-track');track.setAttribute('role','img');track.setAttribute('aria-label',`${axis.left} ${axis.leftPct}%，${axis.right} ${axis.rightPct}%`);
    const fill=node('div','axis-fill');fill.style.width=axis.leftPct+'%';track.append(fill);
    cell.append(h,labels,track,node('p','',axis.text));grid.append(cell);
  });section.append(grid);return section;
}
function renderResult(){
  cancelAdvance();
  try{state.evaluation=Scoring.evaluateAssessment(DATA,state.answers);state.report=Report.create(state.evaluation,DATA.report_profiles);}catch(error){toast('还有题目未完成，请检查后再试。');return;}
  const model=state.report,root=$('report');root.replaceChildren();
  const hero=node('header','report-hero'+(model.type?'':' text-only'));const copy=node('div','hero-copy');const h1=node('h1','',model.quality?'你的人格':'本次作答');h1.id='resultTitle';h1.tabIndex=-1;
  const review=node('button','text-button','回看答案');review.id='reviewAnswers';review.type='button';review.addEventListener('click',()=>showQuestions(state.pages.length-1,DATA.item_count-1));
  const restart=node('button','text-button','重新测试');restart.id='restart';restart.type='button';restart.addEventListener('click',()=>openDialog($('restartDialog')));
  $('resultTools').replaceChildren(review,restart);
  copy.append(h1,node('div','type-code'+(model.type?'':' balanced'),model.title),node('p','result-summary',model.summary));hero.append(copy);
  if(model.type){const asset=DATA.yuanbao_mascots[model.type];hero.append(image(asset.src,asset.alt,'hero-image'));}
  root.append(hero);
  if(model.quality)root.append(axesPanel(model));
  if(model.profile){
    const p=model.profile,portrait=node('div','portrait-grid'),left=node('section','panel portrait-left');
    ['core','strengths','watch'].forEach(key=>{const part=node('section','portrait-section');part.append(title(Report.SECTION_TITLES[key]),body(p[key]));left.append(part);});
    portrait.append(left,contentPanel('communication',p,true),contentPanel('decision',p,true));root.append(portrait);
    const scenarios=node('section','scenario-section');scenarios.setAttribute('aria-label','场景表现');const line=node('div','scenario-connection');line.setAttribute('aria-hidden','true');const grid=node('div','scenario-grid');
    ['work','team','relationship'].forEach((key,index)=>{const c=node('section','scenario '+key);c.append(image(DATA.icons[['pinPink','pinGold','pinBlue'][index]],'','pin'),node('h3','',Report.SECTION_TITLES[key]),body(p[key]));grid.append(c);});
    scenarios.append(line,grid);root.append(scenarios);
    const growth=node('div','growth-grid');growth.append(contentPanel('growth',p,true),contentPanel('reflection',p,true));root.append(growth);
  }else{
    const section=node('section','panel balance-panel');section.append(title(model.quality?'给自己一点观察空间':'先回看你的作答','h2'));
    if(model.quality){
      section.append(body('有些时候，你会因情境不同采取不同方式。这里保留本次测量的真实比例，不替你选择一个确定标签。你可以回看相关题目，也可以先带着这份维度报告继续观察。'));
      const actions=node('div','balance-actions');
      model.balanced.forEach(key=>{const b=node('button','button secondary',`回看${Report.AXIS_META[key].title}题目`);b.type='button';b.addEventListener('click',()=>{const trait=state.evaluation.axes.find(a=>a.key===key).trait;const i=DATA.items.findIndex(item=>item.trait===trait);showQuestions(state.locate(i),i);});actions.append(b);});section.append(actions);
    }else{
      section.append(body('相同答案不等于某一种人格。以下只保留原始维度均值，暂不展开性格画像。你可以回看答案，也可以重新测试。'));
      const list=node('ul','quality-scores'),names={extraversion:'外向性',agreeableness:'宜人性',conscientiousness:'尽责性',neuroticism:'情绪敏感性',imagination:'智性与想象'};
      Object.entries(names).forEach(([key,label])=>{const li=node('li');li.append(node('span','',label),node('span','',`${(state.evaluation.scores[key].mean_x100/100).toFixed(2)} / 5`));list.append(li);});section.append(list);
    }root.append(section);
  }
  const actions=node('div','report-actions');const copyButton=node('button','button secondary','复制给元宝');copyButton.id='copyResult';copyButton.type='button';copyButton.addEventListener('click',copyResult);
  const poster=node('button','button primary','保存或分享图片');poster.id='generatePoster';poster.type='button';poster.addEventListener('click',generatePoster);actions.append(copyButton,poster);root.append(actions);
  $('questionScreen').hidden=true;$('resultScreen').hidden=false;document.body.classList.remove('quiz-mode','quiz-needs-scroll');window.scrollTo({top:0,behavior:'auto'});h1.focus({preventScroll:true});
  persist('result');
}
function transferText(){return Scoring.formatTransferText(Scoring.buildTransferModel(DATA,state.evaluation));}
async function copyResult(){
  if(!state.evaluation||state.copyBusy)return;state.copyBusy=true;const button=$('copyResult');button.disabled=true;
  const text=transferText();$('copyFallback').value=text;let copied=false;
  try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text);copied=true;}}catch(error){/* Fall back to user-visible native selection. */}
  if(!copied){const area=node('textarea');area.value=text;area.setAttribute('readonly','');area.style.cssText='position:fixed;left:0;top:0;opacity:0;font-size:16px';document.body.append(area);area.select();area.setSelectionRange(0,text.length);try{copied=document.execCommand('copy')===true;}catch(error){}area.remove();button.focus({preventScroll:true});}
  if(copied)toast('已复制结果，粘贴回对话即可继续解读。');else{toast('浏览器未允许自动复制，请手动复制。');openDialog($('copyDialog'));$('copyFallback').focus();$('copyFallback').select();}
  state.copyBusy=false;button.disabled=false;
}
function openDialog(dialog){if(typeof dialog.showModal==='function')dialog.showModal();else{dialog.setAttribute('open','');dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');}}
function closeDialog(dialog){if(typeof dialog.close==='function')dialog.close();else dialog.removeAttribute('open');}
function waitForImage(img){if(img.complete)return img.naturalWidth>0?Promise.resolve():Promise.reject(new Error('图片加载失败'));return new Promise((resolve,reject)=>{const finish=error=>{clearTimeout(timer);img.removeEventListener('load',loaded);img.removeEventListener('error',failed);error?reject(error):resolve();};const loaded=()=>finish();const failed=()=>finish(new Error('图片加载失败'));const timer=setTimeout(()=>finish(new Error('图片加载超时')),8000);img.addEventListener('load',loaded);img.addEventListener('error',failed);});}
async function generatePoster(){
  if(state.posterBusy||!state.report)return;
  if(state.posterUrl){try{await showPoster();}catch{toast('图片加载失败，请重试。');}return;}
  state.posterBusy=true;const evaluationSnapshot=state.evaluation,reportSnapshot=state.report;const button=$('generatePoster');button.disabled=true;button.textContent='正在生成…';let host;
  try{
    if(typeof html2canvas!=='function')throw new Error('导出组件不可用');
    if(document.fonts&&document.fonts.ready)await document.fonts.ready;
    host=node('div','poster-export-host');host.setAttribute('aria-hidden','true');const clone=$('reportCapture').cloneNode(true);clone.classList.add('poster-export');clone.querySelectorAll('[id]').forEach(e=>e.removeAttribute('id'));clone.removeAttribute('id');clone.querySelectorAll('button,[hidden]').forEach(e=>e.remove());host.append(clone);document.body.append(host);
    await Promise.all([...clone.querySelectorAll('img')].map(img=>waitForImage(img).catch(()=>{if(img.classList.contains('hero-image'))img.parentElement.classList.add('text-only');if(img.parentElement.classList.contains('illustration-slot'))img.parentElement.remove();else img.remove();})));
    const canvas=await html2canvas(clone,{scale:2,backgroundColor:'#f5f8ef',useCORS:false,allowTaint:false,logging:false,windowWidth:1100,windowHeight:1000,scrollX:0,scrollY:0,imageTimeout:8000});
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));canvas.width=1;canvas.height=1;
    if(!blob)throw new Error('浏览器未能导出图片');
    if(state.evaluation!==evaluationSnapshot||state.report!==reportSnapshot)return;
    state.posterUrl=URL.createObjectURL(blob);
    await showPoster();
  }catch(error){toast('报告图片生成失败，请重试；也可以先复制结果。');}finally{if(host)host.remove();state.posterBusy=false;button.disabled=false;button.textContent='保存或分享图片';}
}
function showPoster(){return globalThis.ResultImage.show({container:$('reportImageMount'),url:state.posterUrl,name:`${state.report.type||'人格倾向'}-人格报告.png`,title:'人格报告图片',trigger:$('generatePoster')});}
$('previousPage').addEventListener('click',()=>showQuestions(state.page-1));
$('resumeQuiz').addEventListener('click',()=>{cancelAdvance();advanceTo(state.resume());});
$('confirmRestart').addEventListener('click',()=>{closeDialog($('restartDialog'));cancelAdvance();clearPoster();Persist.clear(DATA);state.answers.clear();state.evaluation=null;state.report=null;showQuestions(0,0,false);});
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>closeDialog($(button.dataset.close))));
$('selectCopy').addEventListener('click',()=>{$('copyFallback').focus();$('copyFallback').select();$('copyFallback').setSelectionRange(0,$('copyFallback').value.length);toast('已选中，请使用系统复制。');});
document.addEventListener('focusin',event=>{if(state.timer&&!$('question-'+(state.active+1))?.contains(event.target)){cancelAdvance();state.reviewing=true;progress();}});
document.addEventListener('keydown',event=>{
  if($('questionScreen').hidden||event.altKey||event.ctrlKey||event.metaKey||event.repeat||document.querySelector('dialog[open]'))return;
  if(['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName))return;
  if(/^[1-5]$/.test(event.key)){event.preventDefault();const item=DATA.items[state.active];const row=$('question-'+item.id);if(row){const button=row.querySelector(`[data-position="${event.key}"]`);choose(item,Number(button.dataset.value),button);}}
});
const scheduleLayout=()=>{clearTimeout(layoutTimer);layoutTimer=setTimeout(layoutQuestions,100);};
window.addEventListener('resize',scheduleLayout);window.visualViewport?.addEventListener('resize',scheduleLayout);
if(document.fonts?.ready)document.fonts.ready.then(scheduleLayout);
try{document.body.classList.add('quiz-mode');$('runtimeNotice').hidden=true;layoutQuestions();if(restored&&(restored.screen==='result'||state.answers.size===DATA.item_count&&!state.reviewing))renderResult();document.documentElement.dataset.assessmentReady='true';}catch(error){document.body.classList.remove('quiz-mode');$('runtimeNotice').hidden=false;$('runtimeNotice').textContent='测评未能初始化，请重新打开页面或联系提供者。';}
})();

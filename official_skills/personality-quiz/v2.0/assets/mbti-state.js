(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)Object.defineProperty(root,'MbtiStateV1',{value:api});
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const keyFor=spec=>'yuanbao:mbti:state:v1:'+spec.artifact_id;
  const validId=id=>typeof id==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id);
  function normalize(spec,value){
    if(!spec||!validId(spec.artifact_id)||!value||value.v!==1||
       value.artifactId!==spec.artifact_id||value.versionId!==spec.version_id||
       !Number.isInteger(spec.item_count)||!Array.isArray(value.answers)||
       !Number.isInteger(value.active)||value.active<0||value.active>=spec.item_count||
       typeof value.reviewing!=='boolean'||!['question','result'].includes(value.screen))return null;
    const answers=new Map();
    for(const entry of value.answers){
      if(!Array.isArray(entry)||entry.length!==2||!Number.isInteger(entry[0])||
         entry[0]<1||entry[0]>spec.item_count||!Number.isInteger(entry[1])||
         entry[1]<1||entry[1]>5||answers.has(entry[0]))return null;
      answers.set(entry[0],entry[1]);
    }
    if(value.screen==='result'&&answers.size!==spec.item_count)return null;
    return {answers,active:value.active,reviewing:value.reviewing,screen:value.screen};
  }
  function read(spec){
    if(!validId(spec?.artifact_id))return null;
    try{return normalize(spec,JSON.parse(localStorage.getItem(keyFor(spec))||'null'));}
    catch{return null;}
  }
  function write(spec,flow,screen='question',active=flow.active){
    if(!validId(spec?.artifact_id))return false;
    const value={v:1,artifactId:spec.artifact_id,versionId:spec.version_id,
      answers:[...flow.answers],active,reviewing:Boolean(flow.reviewing),screen};
    if(!normalize(spec,value))return false;
    try{localStorage.setItem(keyFor(spec),JSON.stringify(value));return true;}
    catch{return false;}
  }
  function clear(spec){
    if(!validId(spec?.artifact_id))return;
    try{localStorage.removeItem(keyFor(spec));}catch{/* Storage can be unavailable. */}
  }
  return Object.freeze({keyFor,normalize,read,write,clear});
});

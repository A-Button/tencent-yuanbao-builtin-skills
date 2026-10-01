(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  if(root) root.MbtiReport=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const AXIS_META={
    EI:{title:'精力取向',left:'E',right:'I',names:{E:'外倾',I:'内倾'},text:{E:'更容易从交流与外部活动中获得能量',I:'更容易通过独处与深入思考恢复能量',X:'社交与独处的偏好在这次作答中相近'}},
    NS:{title:'信息取向',left:'N',right:'S',names:{N:'直觉',S:'实感'},text:{N:'更关注意义、关联和未来可能性',S:'更关注具体事实、细节与实际经验',X:'抽象探索与具体经验的倾向相近'}},
    FT:{title:'决策取向',left:'T',right:'F',names:{T:'思考',F:'情感'},text:{T:'倾向于先检视逻辑、标准和现实依据',F:'倾向于先考虑价值、关系与对人的影响',X:'逻辑标准与人的感受都会进入决策'}},
    JP:{title:'生活方式',left:'J',right:'P',names:{J:'判断',P:'知觉'},text:{J:'更偏好清晰安排与可预期的推进节奏',P:'更偏好保留选项，随新信息灵活调整',X:'明确安排与灵活调整的倾向相近'}}
  };
  const SECTION_TITLES={core:'核心倾向',strengths:'主要优势',watch:'需要留意',communication:'沟通方式',decision:'决策方式',work:'工作与学习',team:'团队协作',relationship:'亲密关系',growth:'成长建议',reflection:'自我观察'};
  function create(evaluation,catalog){
    if(!evaluation||evaluation.axes.length!==4) throw new Error('报告数据不完整');
    const balanced=evaluation.axes.filter(a=>a.letter==='X');
    const quality=evaluation.quality==='pass';
    const type=quality&&balanced.length===0?evaluation.type_code:null;
    const axes=evaluation.axes.map(a=>{
      const m=AXIS_META[a.key];
      return {...m,key:a.key,letter:a.letter,displayLetter:a.letter==='X'?'倾向接近':a.letter,leftPct:a.highLetter===m.left?a.high:a.low,rightPct:a.highLetter===m.right?a.high:a.low,text:m.text[a.letter],weak:a.letter!=='X'&&Math.abs(a.high-50)<=5};
    });
    if(type&&!catalog.types[type]) throw new Error('缺少对应类型的报告');
    return {type,quality,balanced:balanced.map(a=>a.key),axes,profile:type?catalog.types[type]:null,title:!quality?'再认识一次自己':type||'倾向接近',summary:!quality?'这次每道题的答案都相同，暂不生成类型结论。你可以回看题目，按真实状态分别作答。':type?catalog.types[type].summary:'有些维度在这次作答中恰好持平。你不必急着把自己归入一种类型，可以先看看各个维度，或回看相关题目。'};
  }
  return Object.freeze({AXIS_META,SECTION_TITLES,create});
});

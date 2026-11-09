/* Presentation-only order/visibility of server-rendered, authorized cards. No fetching or private values in storage. */
(()=>{
 'use strict';const KEY='project2:profile-layout:v1';
 const initialized=new WeakSet();
 function init(root){
  if(initialized.has(root))return;initialized.add(root);
  const grid=root.querySelector('[data-profile-cards]'),cards=[...grid.querySelectorAll(':scope > [data-profile-card]')];
  const defaults=cards.map(c=>c.dataset.profileCard),byId=new Map(cards.map(c=>[c.dataset.profileCard,c]));
  let state={order:[...defaults],hidden:[]};
  try{const raw=localStorage.getItem(KEY);if(raw&&raw.length<5000){const value=JSON.parse(raw);if(value.version===1&&Array.isArray(value.order)&&Array.isArray(value.hidden)){state.order=[...new Set(value.order.filter(id=>byId.has(id))),...defaults.filter(id=>!value.order.includes(id))];state.hidden=[...new Set(value.hidden.filter(id=>byId.has(id)))];}}}catch(_){}
  const choices=root.querySelector('[data-profile-layout-choices]');
  function save(){try{localStorage.setItem(KEY,JSON.stringify({version:1,...state}));}catch(_){root.querySelector('[data-profile-layout-message]').textContent='Зміни застосовано, але браузер не дозволяє їх зберегти.';}}
  function render(){for(const id of state.order){const card=byId.get(id);grid.append(card);card.hidden=state.hidden.includes(id);}
   choices.replaceChildren(...state.order.map((id,index)=>{
    const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!state.hidden.includes(id);check.addEventListener('change',()=>{state.hidden=check.checked?state.hidden.filter(k=>k!==id):[...state.hidden,id];save();render();});
    label.append(check,document.createTextNode(' '+byId.get(id).dataset.cardLabel+' '));
    for(const [text,delta] of [['↑',-1],['↓',1]]){const button=document.createElement('button');button.type='button';button.className='btn btn-sm btn-outline-secondary';button.textContent=text;button.disabled=index+delta<0||index+delta>=state.order.length;button.setAttribute('aria-label',byId.get(id).dataset.cardLabel+': перемістити '+(delta<0?'вище':'нижче'));button.addEventListener('click',()=>{[state.order[index],state.order[index+delta]]=[state.order[index+delta],state.order[index]];save();render();});label.append(button);}return label;
   }));
  }
  root.querySelector('[data-profile-layout-reset]').addEventListener('click',()=>{state={order:[...defaults],hidden:[]};save();render();});render();
 }
 const scan=()=>document.querySelectorAll('[data-profile-layout]').forEach(init);scan();
 const target=document.getElementById('profile-overview');if(target)new MutationObserver(scan).observe(target,{childList:true});
})();

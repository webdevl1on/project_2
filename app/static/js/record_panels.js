/* List + detail using original nodes. No cloning, requests or changes to record values. */
(()=>{
 'use strict';const roots=new WeakSet(),wrapped=new WeakSet();let serial=0;
 function mount(root){
  if(roots.has(root))return;roots.add(root);root.classList.add('ui-record-workspace');const group='ui-record-group-'+(++serial);
  const cards=()=>[...root.querySelectorAll(':scope > details,:scope > article > details[data-record-card]')];
  function size(){const selected=cards().find(n=>n.open),body=selected?.querySelector(':scope > .ui-record-body');root.style.minHeight=innerWidth>=1100&&body?body.getBoundingClientRect().height+'px':'';}
  const resize=new ResizeObserver(()=>requestAnimationFrame(size)),observed=new Set();
  function scan(){for(const node of observed)if(!root.contains(node)){resize.unobserve(node);observed.delete(node);}for(const card of cards()){
   if(wrapped.has(card))continue;wrapped.add(card);const summary=card.querySelector(':scope > summary');if(!summary)continue;card.setAttribute('name',group);
   summary.title=summary.textContent;const body=document.createElement('div');body.className='ui-record-body';for(const node of [...card.childNodes])if(node!==summary)body.append(node);card.append(body);resize.observe(body);observed.add(body);
  }size();}
  root.addEventListener('toggle',event=>{if(!cards().includes(event.target))return;if(event.target.open)for(const card of cards())if(card!==event.target)card.open=false;size();},true);
  new MutationObserver(scan).observe(root,{childList:true});addEventListener('resize',size);scan();
 }
 function scan(){document.querySelectorAll('[data-document-current-list],[data-document-archive-list],[data-medical-list],[data-additional-list]').forEach(mount);}
 document.addEventListener('profile:records-loaded',scan);scan();
})();

/* One editor and one existing Person Picker for the complete position list. */
(() => {
 'use strict';
 const editor=document.getElementById('history-editor');if(!editor)return;
 const form=editor.querySelector('form'),state=document.getElementById('history-state');
 const records=JSON.parse(document.getElementById('history-records').textContent);
 const modal=node=>bootstrap.Modal.getOrCreateInstance(node);
 const reset=node=>{node.reset();node.querySelectorAll('[data-history-form-error]').forEach(n=>n.hidden=true);node.querySelectorAll('.is-invalid').forEach(n=>{n.classList.remove('is-invalid');n.removeAttribute('aria-invalid');});};
 const title=(record)=>`${record.person_label} · ${record.position_label} · ${ProfileDates.format(record.assigned_from)} — ${record.assigned_to?ProfileDates.format(record.assigned_to):'по цей час'}`;
 document.querySelector('[data-history-version]')?.addEventListener('change',event=>event.target.form.requestSubmit());
 document.querySelectorAll('[data-history-add],[data-history-edit]').forEach(button=>button.addEventListener('click',()=>{
  reset(form);const record=records[button.dataset.historyEdit];
  form.action=record?`/staff/assignments/${record.id}/correct`:'/staff/assignments/create';
  form.elements.position_id.value=record?.staff_position_id||button.dataset.historyAdd;
  for(const [key,value] of Object.entries(record||{}))if(form.elements[key])form.elements[key].value=value??'';
  const picker=form.querySelector('[data-person-picker]');
  picker.querySelector('[data-person-value]').value=record?.person_id||'';
  picker.querySelector('[data-person-label]').textContent=record?.person_label||'Оберіть військовослужбовця';
  editor.querySelector('[data-history-position]').textContent=record?.position_label||button.dataset.positionLabel;
  editor.querySelector('#history-editor-title').textContent=record?'Редагувати призначення':'Додати призначення';
  form.querySelector('[data-transfer-orders]').hidden=Boolean(record);
  form.querySelector('[data-legacy-future]').hidden=!record||record.assigned_from<=new Date(Date.now()+86400000).toLocaleDateString('en-CA',{timeZone:'Europe/Kyiv'});
  for(const input of form.querySelectorAll('[name^=transfer_release_]'))input.dataset.manual='';
  modal(editor).show();
 }));
 for(const suffix of ['number','date']){
  const source=form.elements[`assignment_order_${suffix}`],target=form.elements[`transfer_release_order_${suffix}`];
  target.addEventListener('input',()=>target.dataset.manual='1');
  source.addEventListener('input',()=>{if(!target.dataset.manual)target.value=source.value;});
 }
 document.querySelectorAll('[data-history-annul],[data-history-restore]').forEach(button=>button.addEventListener('click',()=>{
  const record=records[button.dataset.historyAnnul||button.dataset.historyRestore],restore=Boolean(button.dataset.historyRestore),f=state.querySelector('form');reset(f);
  f.action=`/staff/assignments/${record.id}/${restore?'restore':'annul'}`;f.elements.revision.value=record.revision;
  f.elements.reason.required=!restore;f.elements.reason.disabled=restore;f.querySelector('[data-annul-reason]').hidden=restore;
  state.querySelector('#history-state-title').textContent=restore?'Відновити призначення':'Анулювати призначення';
  state.querySelector('[data-history-state-description]').textContent=title(record);modal(state).show();
 }));
 document.querySelectorAll('[data-history-audit]').forEach(button=>button.addEventListener('click',async()=>{
  const node=document.getElementById('history-audit'),content=node.querySelector('[data-audit-content]');content.textContent='Завантаження…';modal(node).show();button.disabled=true;
  try{const response=await fetch(`/staff/assignments/${button.dataset.historyAudit}/audit`);if(!response.ok)throw Error('Не вдалося завантажити історію.');content.innerHTML=await response.text();}
  catch(error){content.textContent=error.message;}finally{button.disabled=false;}
 }));
 // Keep the editor mounted during confirmation so errors and cancellation preserve its draft.
 const transfer=document.getElementById('history-transfer'),review=transfer.querySelector('.modal-body');
 review.hidden=true;editor.querySelector('.modal-body').append(review);transfer.remove();
 let decision=null;
 review.querySelector('[data-transfer-confirm]').addEventListener('click',()=>decision?.(true));
 review.querySelector('[data-transfer-back]').addEventListener('click',()=>decision?.(false));
 editor.addEventListener('hidden.bs.modal',()=>decision?.(false));
 window.StaffHistory={async submit(node){
  const headers={Accept:'application/json'};
  if(node!==form||!new URL(form.action).pathname.endsWith('/create'))return fetch(node.action,{method:'POST',body:new FormData(node),headers});
  const response=await fetch('/staff/assignments/prepare',{method:'POST',body:new FormData(form),headers});
  if(!response.ok)return response;
  const prepared=await response.json();
  if(prepared.noop)return new Response(JSON.stringify({detail:'Військовослужбовець уже призначений на цю посаду.'}),{status:409,headers:{'content-type':'application/json'}});
  let confirmed=false;
  if(prepared.requires_confirmation){
   review.querySelector('[data-transfer-message]').textContent=prepared.message;form.hidden=true;review.hidden=false;
   try{confirmed=await new Promise(resolve=>decision=resolve);}finally{decision=null;review.hidden=true;form.hidden=false;}
   if(!confirmed)return null;
  }
  const data=new FormData();data.set('token',prepared.token);data.set('confirmed',String(confirmed));data.set('q',form.elements.q.value);
  return fetch('/staff/assignments/confirm',{method:'POST',body:data,headers});
 }};
})();

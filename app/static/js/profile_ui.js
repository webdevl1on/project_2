/* Shared profile record editor lifecycle and one accessible, reusable toast. */
(() => {
 'use strict';
 let timer;
 function toast(message) {
  let node=document.querySelector('[data-profile-toast]');
  if(!node){
   const host=document.createElement('div');host.className='toast-container position-fixed bottom-0 end-0 p-3';
   node=document.createElement('div');node.className='toast';node.dataset.profileToast='';node.dataset.medicalToast='';node.setAttribute('role','status');node.setAttribute('aria-live','polite');node.setAttribute('aria-atomic','true');
   const body=document.createElement('div');body.className='toast-body';node.append(body);host.append(node);document.body.append(host);
  }
  node.querySelector('.toast-body').textContent=message;
  clearTimeout(timer);
  if(globalThis.bootstrap?.Toast)bootstrap.Toast.getOrCreateInstance(node,{delay:3000,autohide:true}).show();
  else{node.classList.add('show');timer=setTimeout(()=>node.classList.remove('show'),3000);}
 }
 function resetForm(form,{preserve=[]}={}) {
  const retained=new Map(preserve.map(name=>[name,form.elements.namedItem(name)?.value]));
  form.reset();
  for(const input of form.elements){
   if(!input.name||preserve.includes(input.name))continue;
   if(input.type==='checkbox'||input.type==='radio')input.checked=false;
   else if(input.tagName==='SELECT')input.selectedIndex=0;
   else if(!['button','submit','reset'].includes(input.type))input.value='';
   input.disabled=false;input.classList.remove('is-invalid');input.setCustomValidity?.('');
  }
  for(const [name,value] of retained)if(form.elements.namedItem(name))form.elements.namedItem(name).value=value;
  for(const key of ['key','id','revision','originalStatus','editing'])delete form.dataset[key];
  form.dispatchEvent(new CustomEvent('profile:reset',{bubbles:true}));
 }
 function openEditor(editor){editor.hidden=false;if(editor.tagName==='DETAILS')editor.open=true;}
 function closeEditor(editor){if(editor.tagName==='DETAILS')editor.open=false;editor.hidden=true;}
 function finishRecord(editor,form,editing,options){resetForm(form,options);closeEditor(editor);toast(editing?'Зміни збережено':'Запис додано');}
 globalThis.ProfileUI={toast,resetForm,openEditor,closeEditor,finishRecord};
})();

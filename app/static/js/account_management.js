/* Account operations retain non-secret drafts and use the shared session/CSRF layer. */
(() => {
 'use strict';
 document.querySelectorAll('[data-account-form]').forEach(form=>{
  let pending=false;const message=form.querySelector('[data-account-error]');
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(pending||!form.reportValidity())return;
   pending=true;message.hidden=true;const button=form.querySelector('button');button.disabled=true;
   try{
    const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{Accept:'application/json'}});
    const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Перевірте заповнення полів.');
    location.assign(data.redirect_to||'/admin/users');
   }catch(error){
    message.textContent=error.message;message.hidden=false;message.tabIndex=-1;message.focus();
    form.querySelectorAll('input[type=password]').forEach(field=>field.value='');
   }finally{pending=false;button.disabled=false;}
  });
 });
})();

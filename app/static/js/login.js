(() => {
 'use strict';const form=document.getElementById('personal-login');if(!form)return;
 const message=form.querySelector('[data-login-error]'),button=form.querySelector('[type=submit]');
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(button.disabled)return;message.hidden=true;button.disabled=true;
  try{
   const response=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});
   const data=await response.json();if(!response.ok)throw Error(data.detail||'Не вдалося увійти.');
   location.assign(data.redirect_to||'/persons');
  }catch(error){message.textContent=error.message;message.hidden=false;form.elements.password.value='';form.elements.password.focus();}
  finally{button.disabled=false;}
 });
})();

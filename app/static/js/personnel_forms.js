/* Common personnel forms: preserve drafts on errors, publish only explicit actions. */
(() => {
    document.addEventListener('submit',async event=>{
        const form=event.target.closest('[data-personnel-form]');if(!form)return;event.preventDefault();
        if(form.dataset.pending)return;
        let message=form.querySelector('[data-personnel-message]');
        if(!message){message=document.createElement('p');message.dataset.personnelMessage='';message.className='text-danger';message.setAttribute('role','alert');message.tabIndex=-1;form.prepend(message);}
        form.dataset.pending='1';const button=event.submitter;if(button)button.disabled=true;
        try {
            const payload=new FormData(form);
            let response=await fetch(form.getAttribute('action'),{method:'POST',body:payload,headers:{Accept:'application/json'}});
            let data=await response.json();if(!response.ok)throw new Error(data.detail||'Не вдалося зберегти.');
            if(form.hasAttribute('data-mirage-convert')){
                if(!window.confirm(data.message))return;
                const confirm=new FormData();confirm.set('token',data.token);confirm.set('confirmed','on');
                response=await fetch(form.getAttribute('action').replace('/prepare','/convert'),{method:'POST',body:confirm});data=await response.json();
                if(!response.ok)throw new Error(data.detail||'Не вдалося оформити.');
            }
            const url=new URL(location.href);url.searchParams.set('personnel_message','Зміни збережено.');history.replaceState(null,'',url.href);location.reload();
        }catch(error){message.textContent=error.message;message.focus();}
        finally{delete form.dataset.pending;if(button)button.disabled=false;}
    });
})();

(() => {
    const root=document.querySelector('#person-contacts');if(!root)return;
    const message=(text,error=false)=>{const box=root.querySelector('[data-contact-message]');box.textContent=text;box.className=error?'alert alert-danger':'alert alert-success';};
    root.addEventListener('click',async event=>{
        const clear=event.target.closest('[data-contact-clear]');
        if(clear){const input=clear.closest('form').elements[clear.dataset.contactClear];input.value='';input.focus();return;}
        const copy=event.target.closest('[data-copy-contact]');if(!copy)return;
        try{await navigator.clipboard.writeText(copy.dataset.copyContact);message('Скопійовано.');}catch(_){message('Не вдалося скопіювати. Виділіть значення й скопіюйте вручну.',true);}
    });
    root.addEventListener('submit',async event=>{
        const form=event.target.closest('[data-contact-form]');if(!form)return;event.preventDefault();
        const action=event.submitter?.value||'save';
        if(action==='archive'&&!window.confirm('Прибрати контакт до архіву?'))return;
        form.querySelectorAll('.is-invalid').forEach(input=>input.classList.remove('is-invalid'));
        form.querySelectorAll('[data-error-for]').forEach(span=>span.textContent='');
        const button=event.submitter;button.disabled=true;root.setAttribute('aria-busy','true');
        const data=new FormData(form);data.set('action',action);
        try{
            const response=await fetch(form.getAttribute('action'),{method:'POST',body:data}),result=await response.json();
            if(!response.ok){
                const field=form.elements[result.field];const error=form.querySelector(`[data-error-for="${result.field}"]`);
                if(error)error.textContent=result.error;else message(result.error,true);
                if(field){field.classList.add('is-invalid');field.focus();}return;
            }
            const list=await fetch(root.dataset.url,{cache:'no-store'});if(!list.ok)throw new Error();root.innerHTML=await list.text();
            message('Контакти збережено.');await window.refreshProfileOverview?.();
        }catch(_){message('Не вдалося завершити збереження. Введені дані залишено; перевірте стан перед повторною спробою.',true);}
        finally{button.disabled=false;root.removeAttribute('aria-busy');}
    });
})();

/* Profile record editors keep the active tab and preserve drafts on failures. */
(() => {
    async function refreshProfileSection(form) {
        const pane=form.closest('.tab-pane')||(form.hasAttribute('data-profile-history-form')?document.getElementById(form.action.includes('/person_ranks/')?'ranks':'names'):null);
        if(!pane||!document.querySelector('#personTabs'))return false;
        const response=await fetch(location.pathname+location.search,{cache:'no-store'});
        if(!response.ok)throw new Error('Запис збережено, але список не вдалося оновити. Оновіть вкладку перед повторним збереженням.');
        const page=new DOMParser().parseFromString(await response.text(),'text/html');
        const updated=page.getElementById(pane.id);
        if(!updated)throw new Error('Запис збережено, але відповідний розділ недоступний.');
        // Close modal before replacing its host; the active Bootstrap tab stays intact.
        const modal=form.closest('.modal');
        if(modal){
            const instance=bootstrap.Modal.getInstance(modal);
            if(instance&&modal.classList.contains('show'))await new Promise(resolve=>{modal.addEventListener('hidden.bs.modal',resolve,{once:true});instance.hide();});
        }
        pane.replaceChildren(...updated.childNodes);
        if(pane.id==='names'||pane.id==='ranks'){
            const id=pane.id==='names'?'addNewName':'addNewRank';
            const current=document.getElementById(id),fresh=page.getElementById(id);
            if(current&&fresh)current.replaceWith(fresh);
        }
        if(pane.id==='service-history'){
            const current=document.getElementById('positions'),fresh=page.getElementById('positions');
            if(current&&fresh)current.replaceChildren(...fresh.childNodes);
        }
        const header=document.querySelector('body > header'),newHeader=page.querySelector('body > header');
        if(header&&newHeader)header.replaceWith(newHeader);
        window.initServiceBasisForms?.(pane);
        window.ProfileDates?.enhance?.(pane);
        window.refreshProfileOverview?.();
        return true;
    }
    document.addEventListener('click',event=>{
        const trigger=event.target.closest('[data-profile-record-open]');if(!trigger)return;
        const editor=document.getElementById(trigger.dataset.profileRecordOpen);if(!editor)return;
        if(trigger.hasAttribute('data-profile-record-new')){
            const form=editor.querySelector('form');if(form){
                if(window.ProfileUI?.resetForm)ProfileUI.resetForm(form,{preserve:['contact_type','person_id','position_id']});else form.reset();
                // Initial currentness is a server-defined default, never copied from an edited row.
                if(form.hasAttribute('data-service-basis-form')&&form.elements.is_current)form.elements.is_current.checked=form.elements.is_current.defaultChecked;
                form.querySelectorAll('[data-personnel-message]').forEach(node=>node.textContent='');
                form.querySelectorAll('[name=revision]').forEach(input=>input.value='');
                form.querySelectorAll('select').forEach(select=>select.dispatchEvent(new Event('change',{bubbles:true})));
                form.dispatchEvent(new Event('change',{bubbles:true}));
            }
        }
        editor.hidden=false;editor.querySelector('input:not([type=hidden]),select,textarea')?.focus();
    });
    document.addEventListener('show.bs.modal',event=>{
        if(!['addNewName','addNewRank'].includes(event.target.id))return;
        const form=event.target.querySelector('form');if(form){ProfileUI.resetForm(form);form.querySelectorAll('[data-personnel-message]').forEach(n=>n.textContent='');}
    });
    document.addEventListener('submit',async event=>{
        const form=event.target.closest('[data-personnel-form],[data-profile-history-form]');if(!form)return;event.preventDefault();
        if(form.dataset.pending)return;
        let message=form.querySelector('[data-personnel-message]');
        if(!message){message=document.createElement('p');message.dataset.personnelMessage='';message.className='text-danger';message.setAttribute('role','alert');message.tabIndex=-1;form.prepend(message);}
        message.textContent='';form.dataset.pending='1';const button=event.submitter;if(button)button.disabled=true;
        try {
            if(form.elements.confirmation&&form.elements.confirmation.value!=='DELETE')throw new Error('Для видалення введіть DELETE.');
            const payload=new FormData(form),path=new URL(form.action).pathname;
            const editing=form.hasAttribute('data-profile-history-form')? !/\/(add_new|add_rank)\//.test(path):!!payload.get('revision');
            let response=await fetch(form.getAttribute('action'),{method:'POST',body:payload,headers:{Accept:'application/json'}});
            const json=(response.headers.get('content-type')||'').includes('application/json');
            let data=json?await response.json():{};
            if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Не вдалося зберегти. Перевірте введені значення.');
            if(form.hasAttribute('data-mirage-convert')){
                if(!window.confirm(data.message))return;
                const confirm=new FormData();confirm.set('token',data.token);confirm.set('confirmed','on');
                response=await fetch(form.getAttribute('action').replace('/prepare','/convert'),{method:'POST',body:confirm});data=await response.json();
                if(!response.ok)throw new Error(data.detail||'Не вдалося оформити.');
            }
            if(await refreshProfileSection(form)){
                window.ProfileUI?.toast(editing?'Зміни збережено':'Запис додано');
                return;
            }
            const url=new URL(location.href);url.searchParams.set('personnel_message','Зміни збережено.');history.replaceState(null,'',url.href);location.reload();
        }catch(error){message.textContent=error.message;message.focus();}
        finally{delete form.dataset.pending;if(button)button.disabled=false;}
    });
})();

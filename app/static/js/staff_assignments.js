(() => {
    'use strict';
    document.querySelectorAll('[data-current-version]').forEach(input=>input.addEventListener('change',()=>{
        const end=input.form.elements.valid_to;
        if(input.checked)end.value='';end.disabled=input.checked;end.required=!input.checked;
    }));
    const context=document.getElementById('position-filters');
    context?.elements.version_id?.addEventListener('change',()=>{
        const selected=context.elements.version_id.selectedOptions[0],on=context.elements.as_of;
        if(!selected?.dataset.validFrom || !on)return;
        if(!on.value || on.value<selected.dataset.validFrom)on.value=selected.dataset.validFrom;
        if(selected.dataset.validTo && on.value>selected.dataset.validTo)on.value=selected.dataset.validTo;
    });
    const modalNode=document.getElementById('staff-assignment-confirm');
    if(!modalNode)return;
    let pending=null;
    async function prepare(form,onlyConfirm=false){
        const status=form.querySelector('[data-assignment-status]');
        const button=form.querySelector('[type=submit]');button.disabled=true;status.textContent='Перевірка…';
        try{
            const response=await fetch('/person-positions/assign/prepare',{method:'POST',body:new FormData(form)});
            const data=await response.json();if(!response.ok)throw Error(data.detail || 'Помилка перевірки.');
            if(data.noop){status.textContent='Військовослужбовець уже призначений на цю посаду.';return;}
            form.elements.token.value=data.token;status.textContent='';
            if(data.requires_confirmation){pending=form;modalNode.querySelector('[data-assignment-confirm-message]').textContent=data.message;bootstrap.Modal.getOrCreateInstance(modalNode).show();}
            else if(!onlyConfirm) await save(form,false);
            else status.textContent='Обрано. Натисніть «Зберегти» для призначення.';
        }catch(error){status.textContent=error.message;}
        finally{button.disabled=false;}
    }
    async function save(form,confirmed){
        const status=form.querySelector('[data-assignment-status]');
        const data=new FormData(form);data.set('confirmed',String(confirmed));
        const response=await fetch('/person-positions/assign',{method:'POST',body:data});
        if(response.redirected){location.assign(response.url);return;}
        const result=await response.json();throw Error(result.detail || 'Не вдалося зберегти призначення.');
    }
    document.querySelectorAll('.person-assignment-form').forEach(form=>{
        form.addEventListener('submit',event=>{event.preventDefault();prepare(form);});
        form.addEventListener('personpicked',event=>{
            if(event.detail.positionId && event.detail.positionId!==form.elements.position_id.value && form.elements.on.value)prepare(form,true);
        });
    });
    modalNode.addEventListener('hidden.bs.modal',()=>{pending=null;});
    const yes=modalNode.querySelector('[data-assignment-confirm-yes]');
    yes.addEventListener('click',async()=>{
        if(!pending)return;yes.disabled=true;const form=pending;
        try{await save(form,true);bootstrap.Modal.getOrCreateInstance(modalNode).hide();}
        catch(error){form.querySelector('[data-assignment-status]').textContent=error.message;bootstrap.Modal.getOrCreateInstance(modalNode).hide();}
        finally{yes.disabled=false;}
    });
})();

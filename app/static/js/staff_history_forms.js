/* Intercept only history POST forms. Errors never replace/reset their DOM. */
(() => {
    'use strict';
    document.querySelectorAll('form[method="post"][action^="/staff/"]').forEach((form,index) => {
        form.noValidate=true;form.classList.add('staff-history-form');
        const message=document.createElement('p');
        message.className='text-danger w-100 mt-2';message.hidden=true;
        message.id=`staff-form-error-${index}`;message.setAttribute('role','alert');
        message.tabIndex=-1;message.dataset.historyFormError='';form.append(message);
        let pending=false;
        const clear=()=>{
            message.hidden=true;
            form.querySelectorAll('[aria-invalid="true"]').forEach(field=>{
                field.classList.remove('is-invalid');field.removeAttribute('aria-invalid');
                const ids=(field.getAttribute('aria-describedby')||'').split(' ').filter(id=>id!==message.id);
                if(ids.length)field.setAttribute('aria-describedby',ids.join(' '));else field.removeAttribute('aria-describedby');
            });
        };
        const show=(text,names=[])=>{
            message.textContent=text;message.hidden=false;
            const fields=names.flatMap(name=>Array.from(form.elements).filter(field=>field.name===name))
                .map(field=>field.type==='hidden' ? field.closest('[data-person-picker]')?.querySelector('[data-person-label]') : field).filter(Boolean);
            fields.forEach(field=>{
                field.classList.add('is-invalid');field.setAttribute('aria-invalid','true');
                field.setAttribute('aria-describedby',`${field.getAttribute('aria-describedby')||''} ${message.id}`.trim());
            });
            (fields[0]||message).focus();
        };
        form.addEventListener('submit',async event=>{
            event.preventDefault();if(pending)return;clear();
            for(const field of form.elements){
                if(field.willValidate && (!field.checkValidity() || (field.required && !field.value.trim()))){
                    show(field.validity.valueMissing || !field.value.trim() ? 'Заповніть обов’язкове поле.' : field.validationMessage,[field.name]);return;
                }
            }
            const person=form.querySelector('[data-person-value]');
            if(person && !person.value){show('Оберіть військовослужбовця.',['person_id']);return;}
            const start=form.elements.assigned_from || form.elements.valid_from;
            const end=form.elements.assigned_to || form.elements.valid_to;
            if(start?.value && end?.value && end.value<start.value){
                show('Дата завершення не може бути раніше дати початку.',[end.name]);return;
            }
            const number=form.elements.position_number;
            if(number && (!/^\+?\d+$/.test(number.value.trim()) || /^\+?0+$/.test(number.value.trim()))){
                show('Номер посади має бути додатним цілим числом.',['position_number']);return;
            }
            const buttons=Array.from(form.querySelectorAll('button')).filter(button=>button.type==='submit');
            pending=true;buttons.forEach(button=>button.disabled=true);form.setAttribute('aria-busy','true');
            try{
                const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{Accept:'application/json'}});
                if(response.ok && response.redirected){location.assign(response.url);return;}
                if((response.headers.get('content-type')||'').includes('application/json')){
                    const data=await response.json();
                    if(Array.isArray(data.detail)){
                        show('Перевірте заповнення обов’язкових полів і формат значень.',data.detail.map(item=>item.loc?.at(-1)).filter(Boolean));
                    }else show(typeof data.detail==='string' ? data.detail : 'Не вдалося зберегти зміни.',data.fields||[]);
                }else show('Сервер не зміг зберегти зміни. Введені значення залишилися у формі.');
            }catch{
                show('Немає зв’язку із сервером або відповідь не отримана. Значення збережено у формі; перевірте результат перед повторним надсиланням.');
            }finally{pending=false;buttons.forEach(button=>button.disabled=false);form.removeAttribute('aria-busy');}
        });
    });
})();

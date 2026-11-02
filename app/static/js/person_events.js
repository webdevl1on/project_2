/* Person-owned history: staff DOM is only an entry point, never an event owner. */
(() => {
    'use strict';
    const modal = document.getElementById('person-events-modal');
    if (!modal) return;
    const form = modal.querySelector('[data-event-form]');
    const editor = modal.querySelector('[data-event-editor]');
    const message = modal.querySelector('[data-events-message]');
    const conflictList = modal.querySelector('[data-events-conflicts]');
    const list = modal.querySelector('[data-events-list]');
    const newButton = modal.querySelector('[data-event-new]');
    let personId = null, model = null, editing = null, saving = false, baseline = '', confirmedType = null, annulling = null;
    const typeConfirm=modal.querySelector('[data-event-type-confirm]'),annulConfirm=modal.querySelector('[data-event-annul-confirm]'),annulForm=modal.querySelector('[data-event-annul-form]');
    const typeIntent=()=>editing?`${editing.event_id}:${editing.event_type_id}:${field('event_type_id').value}`:null;
    const values = () => JSON.stringify([...new FormData(form)]);
    const dirty = () => !editor.hidden && values() !== baseline;
    const endpoint = () => `/persons/${personId}/events`;
    const field = name => form.elements.namedItem(name);
    function notice(text, failed = false) {
        message.textContent = text;
        message.className = text ? `alert alert-${failed ? 'danger' : 'success'}` : '';
    }
    function clearErrors() {
        form.querySelectorAll('.is-invalid').forEach(input => { input.classList.remove('is-invalid'); input.removeAttribute('aria-invalid'); const display=form.querySelector(`[data-exact-date-for="${input.name}"]`); display?.classList.remove('is-invalid'); display?.removeAttribute('aria-invalid'); });
        conflictList.replaceChildren(); conflictList.hidden = true;
    }
    function showError(data) {
        notice(data.detail || 'Не вдалося виконати операцію.', true);
        for (const row of data.conflicts || []) {
            const item = document.createElement('li');
            item.textContent = `${row.type_name}${row.subtype_name ? ' · ' + row.subtype_name : ''}: ${row.period}`;
            conflictList.append(item);
        }
        conflictList.hidden = !conflictList.childElementCount;
        const input = data.field && field(data.field);
        if (input) { const target=form.querySelector(`[data-exact-date-for="${input.name}"]`) || input; target.classList.add('is-invalid'); target.setAttribute('aria-invalid', 'true'); target.focus(); }
    }
    function option(select, value, text) { select.add(new Option(text, String(value ?? ''))); }
    function subtypes(selected = '') {
        const select = field('event_subtype_id'); select.replaceChildren();
        option(select, '', 'Без підтипу');
        const kind = model.types.find(row => String(row.id) === field('event_type_id').value);
        for (const sub of kind?.subtypes || []) {
            if (sub.active || sub.id === editing?.event_subtype_id) option(select, sub.id, sub.name + (sub.active ? '' : ' (неактивний)'));
        }
        select.value = [...select.options].some(row => row.value === String(selected)) ? String(selected) : '';
    }
    function typeOptions(selected = '') {
        const select = field('event_type_id'); select.replaceChildren(); option(select, '', 'Оберіть тип');
        for (const kind of model.types) {
            if (kind.active || kind.id === editing?.event_type_id) option(select, kind.id, kind.name + (kind.active ? '' : ' (неактивний)'));
        }
        select.value = String(selected || '');
    }
    function openEditor(record = null) {
        if (saving || (dirty() && !window.confirm('Відхилити незбережені зміни події?'))) return;
        if(record?.annulled_at)return;
        confirmedType=null;typeConfirm.hidden=true;
        editing = record; form.reset(); clearErrors(); notice('');
        typeOptions(record?.event_type_id); subtypes(record?.event_subtype_id || '');
        for (const input of form.elements) if (input.name && !input.name.endsWith('_id')) { if(input.type==='checkbox')input.checked=Boolean(record?.[input.name]); else input.value = record?.[input.name] ?? ''; }
        modal.querySelector('[data-event-editor-title]').textContent = record ? 'Редагування події' : 'Нова подія';
        editor.hidden = false; baseline = values(); field('event_type_id').focus();
    }
    const displayDate = value => value ? value.split('-').reverse().join('.') : '';
    const timestamp = value => value ? new Intl.DateTimeFormat('uk-UA',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false,timeZone:'UTC'}).format(new Date(value))+' UTC' : '';
    const make = (tag,text) => {const el=document.createElement(tag);if(text!=null)el.textContent=text;return el;};
    function correctionHistory(record){
        const history=make('details');history.className='small mt-2';history.append(make('summary',`Історія виправлень (${record.corrections.length})`));
        for(const row of record.corrections){const line=make('p');line.className='mb-1';line.textContent=(row.operation==='type_change'?`Тип: «${row.before.type_name}» → «${row.after.type_name}»`:'Анулювання')+' · '+timestamp(row.occurred_at)+' · '+(row.actor_name || (row.actor_id?'Користувач №'+row.actor_id:'Автор невідомий'));history.append(line);}
        return history;
    }
    function renderArchive(records,container,view=null){
        if(!records?.length)return;
        const archive=make('details');archive.dataset.eventAnnulledArchive='';archive.className='event-annulled-archive mt-3';archive.append(make('summary',`Архів анульованих подій (${records.length})`));
        for(const record of records){const card=make('article');card.dataset.annulledEventId=record.event_id;card.className='border rounded p-2 mt-2 bg-light text-secondary';
            card.append(make('strong','Анульовано · '+record.type_name+(record.subtype_name?' · '+record.subtype_name:'')),make('p',record.period),make('p','Причина: '+record.annulment_reason),make('p',timestamp(record.annulled_at)+' · '+(record.annulled_by?'Користувач №'+record.annulled_by:'Автор невідомий')));
            if(record.corrections?.length)card.append(correctionHistory(record));
            if(view){const button=make('button','Історія виправлень');button.type='button';button.className='btn btn-sm btn-outline-secondary';button.addEventListener('click',()=>view(record));card.append(button);}
            archive.append(card);
        }
        container.append(archive);
    }
    function requestAnnul(record){
        if(saving||record.annulled_at)return;annulling=record;annulForm.reset();annulForm.querySelector('[data-event-annul-error]').textContent='';
        modal.querySelector('[data-event-annul-description]').textContent=record.type_name+' · '+record.period+'. Анулюється збережений запис; чернетка не записується.';
        annulConfirm.hidden=false;annulForm.elements.reason.focus();
    }
    function render() {
        list.replaceChildren();
        if (!model.events.length) { const empty = document.createElement('p'); empty.textContent = 'Активних або завершених подій немає.'; list.append(empty); }
        for (const record of model.events) {
            const card = document.createElement('article'); card.className = 'border rounded p-2 mb-2'; card.dataset.eventId = record.event_id;
            const title = document.createElement('strong'); title.textContent = record.type_name + (record.subtype_name ? ' · ' + record.subtype_name : '');
            const color = model.types.find(kind => kind.id === record.event_type_id)?.color;
            if (color && CSS.supports('border-color', color)) card.style.borderLeft = `4px solid ${color}`;
            const period = document.createElement('p'); period.className = 'mb-1'; period.textContent = (record.mirage ? 'Міраж · ' : '') + record.period + (record.legacy_future_end ? ' — перевірте стару майбутню дату у фактичному полі; плановий строк тепер задається окремо' : '');
            const detail = document.createElement('dl'); detail.className = 'small mb-1';
            for (const name of ['duration', 'order_date', 'planned_end', 'order_number', 'purpose', 'location', 'note', 'event_status']) {
                if (record[name] === null || record[name] === '') continue;
                const label = document.createElement('dt'), value = document.createElement('dd');
                label.textContent = field(name).closest('label').firstChild.textContent.trim();
                value.textContent = ['order_date','planned_end'].includes(name) ? displayDate(record[name]) : String(record[name]);
                value.style.whiteSpace = 'pre-wrap'; detail.append(label, value);
            }
            const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'btn btn-sm btn-outline-primary';
            edit.textContent = 'Редагувати'; edit.dataset.eventEdit = record.event_id; edit.disabled = saving;
            edit.addEventListener('click', () => openEditor(record)); card.append(title, period, detail, edit);
            if (!record.completion_confirmed && !record.mirage) { const confirm=document.createElement('button');confirm.type='button';confirm.className='btn btn-sm btn-outline-success ms-2';confirm.dataset.eventConfirm=record.event_id;confirm.textContent='Підтвердити завершення / повернення';confirm.addEventListener('click',()=>{openEditor(record);field('completion_confirmed').checked=true;field('duration').value='';field('date_end').value=record.planned_end && record.planned_end<=model.today ? record.planned_end : '';field('date_end').focus();});card.append(confirm); }
            const annul=make('button','Анулювати');annul.type='button';annul.className='btn btn-sm btn-outline-danger ms-2';annul.dataset.eventAnnul=record.event_id;annul.disabled=saving;annul.addEventListener('click',()=>requestAnnul(record));card.append(annul);
            if(record.corrections?.length)card.append(correctionHistory(record));
            list.append(card);
        }
        renderArchive(model.annulled,list);
    }
    async function load() {
        const pid = personId;
        const response = await fetch(endpoint(), { headers: { Accept: 'application/json' }, cache: 'no-store' });
        const data = await response.json(); if (!response.ok) throw Error(data.detail || 'Не вдалося завантажити події.');
        if (pid !== personId) return;
        model = data; newButton.disabled = saving; render();
    }
    async function open(id, label, options = {}) {
        const nextId = String(id);
        if (saving || (personId !== nextId && dirty() && !window.confirm('Відхилити незбережені зміни події?'))) return;
        if (personId !== nextId) {
            personId = nextId; model = null; editing = null;annulling=null;annulConfirm.hidden=true;typeConfirm.hidden=true; editor.hidden = true; form.reset(); clearErrors(); list.replaceChildren();
        }
        modal.querySelector('[data-events-person]').textContent = label || 'Військовослужбовець';
        newButton.disabled = true; notice('Завантаження…'); bootstrap.Modal.getOrCreateInstance(modal).show();
        try {
            await load(); if (personId !== nextId) return; notice('');
            if(options.annulId){const record=model.events.find(r=>r.event_id===Number(options.annulId));if(record)requestAnnul(record);}
            else if(options.archiveId){const archive=list.querySelector('[data-event-annulled-archive]');if(archive){archive.open=true;archive.querySelector(`[data-annulled-event-id="${Number(options.archiveId)}"]`)?.scrollIntoView({block:'nearest'});}}
            else if (options.eventId) {
                const record = model.events.find(row => row.event_id === Number(options.eventId));
                if (record) openEditor(record); else notice('Подію не знайдено в актуальній історії.', true);
            } else if (options.create) openEditor();
        } catch (error) { notice(error.message, true); }
    }
    globalThis.PersonEvents = {open,renderArchive};
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-events-open]'); if (!button) return;
        event.preventDefault(); event.stopPropagation();
        open(button.dataset.personId, button.dataset.eventsPersonLabel, {eventId:button.dataset.eventsEventId});
    });
    field('event_type_id').addEventListener('change', () => {confirmedType=null;typeConfirm.hidden=true;subtypes(field('event_subtype_id').value);});
    modal.querySelector('[data-event-type-no]').addEventListener('click',()=>{typeConfirm.hidden=true;confirmedType=null;field('event_type_id').focus();});
    modal.querySelector('[data-event-type-yes]').addEventListener('click',()=>{confirmedType=typeIntent();typeConfirm.hidden=true;form.requestSubmit();});
    modal.querySelector('[data-event-annul-no]').addEventListener('click',()=>{if(!saving){annulConfirm.hidden=true;annulling=null;}});
    form.addEventListener('input', event => { event.target.classList.remove('is-invalid'); event.target.removeAttribute('aria-invalid'); });
    newButton.addEventListener('click', () => model && openEditor());
    modal.querySelector('[data-event-cancel]').addEventListener('click', () => {
        if (saving || (dirty() && !window.confirm('Відхилити незбережені зміни події?'))) return;
        editor.hidden = true; editing = null; clearErrors(); notice('');
    });
    modal.querySelector('[data-events-reload]').addEventListener('click', async () => {
        try { await load(); notice('Список оновлено. Введені поля збережено.'); } catch (error) { notice(error.message, true); }
    });
    function submission(){const data=new FormData(form);data.set('completion_confirmed',field('completion_confirmed').checked?'1':'0');data.set('confirm_type_change',confirmedType===typeIntent()?'1':'0');return data;}
    annulForm.addEventListener('submit',async event=>{
        event.preventDefault();if(saving||!annulling||!annulForm.reportValidity())return;
        const target=annulling,button=annulForm.querySelector('[type=submit]'),error=annulForm.querySelector('[data-event-annul-error]');
        error.textContent='';if(!annulForm.elements.reason.value.trim()){error.textContent='Укажіть причину анулювання.';annulForm.elements.reason.focus();return;}
        saving=true;button.disabled=true;
        try{const data=new FormData(annulForm);data.set('expected_state',target.expected_state);const response=await fetch(endpoint()+`/${target.event_id}/annul`,{method:'POST',body:data,headers:{Accept:'application/json'}});const result=await response.json();if(!response.ok){error.textContent=result.detail;annulForm.elements.reason.focus();return;}
            annulConfirm.hidden=true;annulling=null;if(editing?.event_id===target.event_id){editor.hidden=true;editing=null;typeConfirm.hidden=true;}
            try{await load();notice(result.message);}catch{notice('Подію анульовано. Оновіть список.');}
            document.dispatchEvent(new CustomEvent('person-events:saved',{detail:{personId:Number(personId),eventId:target.event_id}}));
        }catch{error.textContent='Не вдалося отримати відповідь сервера. Причину збережено; перевірте історію перед повтором.';}
        finally{saving=false;button.disabled=false;render();}
    });
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (saving) return; clearErrors(); notice('');
        if (!form.reportValidity()) return;
        if (field('date_end').value && field('date_end').value < field('date_start').value) {
            showError({ detail: 'Дата завершення не може бути раніше дати початку.', field: 'date_end' }); return;
        }
        if(field('planned_end').value && field('planned_end').value<field('date_start').value){showError({detail:'Орієнтовне завершення не може бути раніше початку.',field:'planned_end'});return;}
        if((field('date_end').value || field('duration').value) && !field('completion_confirmed').checked){showError({detail:'Підтвердьте фактичне завершення або внесіть строк як орієнтовний.',field:'completion_confirmed'});return;}
        if(editing && String(editing.event_type_id)!==field('event_type_id').value && confirmedType!==typeIntent()){
            modal.querySelector('[data-event-type-confirm-text]').textContent=`Підтверджуєте зміну типу події з «${editing.type_name}» на «${field('event_type_id').selectedOptions[0]?.textContent}»?`;
            typeConfirm.hidden=false;typeConfirm.focus();return;
        }
        saving = true; newButton.disabled = true; const submit = form.querySelector('[type=submit]'); submit.disabled = true;
        try {
            const response = await fetch(endpoint() + (editing ? `/${editing.event_id}` : ''), { method: 'POST', body: submission(), headers: { Accept: 'application/json' } });
            const data = await response.json(); if (!response.ok) { showError(data); return; }
            editor.hidden = true; editing = null;
            // Saving is already successful even if the subsequent list request fails.
            try { await load(); notice(data.message); } catch { notice('Подію збережено. Не вдалося оновити список; натисніть «Оновити список».'); }
            document.dispatchEvent(new CustomEvent('person-events:saved', {detail: {personId: Number(personId), eventId: data.event_id}}));
        } catch { notice('Не вдалося отримати відповідь сервера. Введені поля збережено; перевірте список перед повторною спробою.', true); }
        finally { saving = false; submit.disabled = false; newButton.disabled = !model; render(); }
    });
})();

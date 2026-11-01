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
    let personId = null, model = null, editing = null, saving = false, baseline = '';
    const values = () => JSON.stringify([...new FormData(form)]);
    const dirty = () => !editor.hidden && values() !== baseline;
    const endpoint = () => `/persons/${personId}/events`;
    const field = name => form.elements.namedItem(name);
    function notice(text, failed = false) {
        message.textContent = text;
        message.className = text ? `alert alert-${failed ? 'danger' : 'success'}` : '';
    }
    function clearErrors() {
        form.querySelectorAll('.is-invalid').forEach(input => { input.classList.remove('is-invalid'); input.removeAttribute('aria-invalid'); });
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
        if (input) { input.classList.add('is-invalid'); input.setAttribute('aria-invalid', 'true'); input.focus(); }
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
        editing = record; form.reset(); clearErrors(); notice('');
        typeOptions(record?.event_type_id); subtypes(record?.event_subtype_id || '');
        for (const input of form.elements) if (input.name && !input.name.endsWith('_id')) input.value = record?.[input.name] ?? '';
        modal.querySelector('[data-event-editor-title]').textContent = record ? 'Редагування події' : 'Нова подія';
        editor.hidden = false; baseline = values(); field('event_type_id').focus();
    }
    const displayDate = value => value ? value.split('-').reverse().join('.') : '';
    function render() {
        list.replaceChildren();
        if (!model.events.length) { const empty = document.createElement('p'); empty.textContent = 'Подій ще немає.'; list.append(empty); }
        for (const record of model.events) {
            const card = document.createElement('article'); card.className = 'border rounded p-2 mb-2'; card.dataset.eventId = record.event_id;
            const title = document.createElement('strong'); title.textContent = record.type_name + (record.subtype_name ? ' · ' + record.subtype_name : '');
            const color = model.types.find(kind => kind.id === record.event_type_id)?.color;
            if (color && CSS.supports('border-color', color)) card.style.borderLeft = `4px solid ${color}`;
            const period = document.createElement('p'); period.className = 'mb-1'; period.textContent = record.period;
            const detail = document.createElement('dl'); detail.className = 'small mb-1';
            for (const name of ['duration', 'order_date', 'order_number', 'purpose', 'location', 'note', 'event_status']) {
                if (record[name] === null || record[name] === '') continue;
                const label = document.createElement('dt'), value = document.createElement('dd');
                label.textContent = field(name).closest('label').firstChild.textContent.trim();
                value.textContent = name === 'order_date' ? displayDate(record[name]) : String(record[name]);
                value.style.whiteSpace = 'pre-wrap'; detail.append(label, value);
            }
            const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'btn btn-sm btn-outline-primary';
            edit.textContent = 'Редагувати'; edit.dataset.eventEdit = record.event_id; edit.disabled = saving;
            edit.addEventListener('click', () => openEditor(record)); card.append(title, period, detail, edit); list.append(card);
        }
    }
    async function load() {
        const pid = personId;
        const response = await fetch(endpoint(), { headers: { Accept: 'application/json' }, cache: 'no-store' });
        const data = await response.json(); if (!response.ok) throw Error(data.detail || 'Не вдалося завантажити події.');
        if (pid !== personId) return;
        model = data; newButton.disabled = saving; render();
    }
    document.addEventListener('click', async event => {
        const button = event.target.closest('[data-events-open]'); if (!button) return;
        event.preventDefault(); event.stopPropagation();
        if (saving || (personId !== button.dataset.personId && dirty() && !window.confirm('Відхилити незбережені зміни події?'))) return;
        if (personId !== button.dataset.personId) {
            personId = button.dataset.personId; model = null; editing = null; editor.hidden = true; form.reset(); clearErrors(); list.replaceChildren();
        }
        modal.querySelector('[data-events-person]').textContent = button.dataset.eventsPersonLabel || 'Військовослужбовець';
        newButton.disabled = true; notice('Завантаження…'); bootstrap.Modal.getOrCreateInstance(modal).show();
        try { await load(); notice(''); } catch (error) { notice(error.message, true); }
    });
    field('event_type_id').addEventListener('change', () => subtypes(field('event_subtype_id').value));
    form.addEventListener('input', event => { event.target.classList.remove('is-invalid'); event.target.removeAttribute('aria-invalid'); });
    newButton.addEventListener('click', () => model && openEditor());
    modal.querySelector('[data-event-cancel]').addEventListener('click', () => {
        if (saving || (dirty() && !window.confirm('Відхилити незбережені зміни події?'))) return;
        editor.hidden = true; editing = null; clearErrors(); notice('');
    });
    modal.querySelector('[data-events-reload]').addEventListener('click', async () => {
        try { await load(); notice('Список оновлено. Введені поля збережено.'); } catch (error) { notice(error.message, true); }
    });
    form.addEventListener('submit', async event => {
        event.preventDefault(); if (saving) return; clearErrors(); notice('');
        if (!form.reportValidity()) return;
        if (field('date_end').value && field('date_end').value < field('date_start').value) {
            showError({ detail: 'Дата завершення не може бути раніше дати початку.', field: 'date_end' }); return;
        }
        saving = true; newButton.disabled = true; const submit = form.querySelector('[type=submit]'); submit.disabled = true;
        try {
            const response = await fetch(endpoint() + (editing ? `/${editing.event_id}` : ''), { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } });
            const data = await response.json(); if (!response.ok) { showError(data); return; }
            editor.hidden = true; editing = null;
            // Saving is already successful even if the subsequent list request fails.
            try { await load(); notice(data.message); } catch { notice('Подію збережено. Не вдалося оновити список; натисніть «Оновити список».'); }
        } catch { notice('Не вдалося отримати відповідь сервера. Введені поля збережено; перевірте список перед повторною спробою.', true); }
        finally { saving = false; submit.disabled = false; newButton.disabled = !model; render(); }
    });
})();

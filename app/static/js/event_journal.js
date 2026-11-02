(() => {
    'use strict';
    const source = document.getElementById('event-journal-data'); if (!source) return;
    let model = JSON.parse(source.textContent), selected = null, generation = 0;
    const rows = document.querySelector('[data-journal-rows]'), message = document.querySelector('[data-journal-message]');
    const all = selector => [...document.querySelectorAll(selector)];
    const node = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
    const current = () => model.people.find(p => p.id === selected);
    function select(id, saveURL = true) {
        selected = id;
        for (const row of rows.querySelectorAll('[data-journal-person-id]')) row.classList.toggle('is-selected', Number(row.dataset.journalPersonId) === id);
        if (saveURL) { const url = new URL(location.href); if (id) url.searchParams.set('person_id', id); else url.searchParams.delete('person_id'); history.replaceState(null, '', url); }
        renderPerson();
    }
    function renderRows() {
        rows.replaceChildren(); document.querySelector('[data-journal-count]').textContent = `${model.people.length} осіб`;
        if (!model.people.length) { const tr = node('tr'), td = node('td', 'За цими фільтрами людей немає.', 'text-center text-secondary p-4'); td.colSpan = model.buckets.length + 5;td.dataset.journalEmpty=''; tr.append(td); rows.append(tr); }
        for (const person of model.people) {
            const tr = node('tr'); tr.dataset.journalPersonId = person.id;
            const number=node('td',String(model.people.indexOf(person)+1));number.dataset.journalExtra='row_number';number.dataset.columnKey='row_number';number.hidden=true;tr.append(number);
            const name = node('td', null, 'event-person-cell'), button = node('button', person.name); button.type = 'button'; button.title = `${person.name} · ${person.birth}`; button.addEventListener('click', () => select(person.id)); name.dataset.columnKey='name';name.append(button);
            const unit = node('td', person.unit, 'event-unit-cell'); unit.title = person.unit;unit.dataset.columnKey='unit';
            tr.append(name, unit);
            for(const key of ['position_number','position_short']){const td=node('td',person[key]??'');td.dataset.journalExtra=key;td.dataset.columnKey=key;td.hidden=true;td.title=person[key]??'';tr.append(td);}
            for (const [index,cell] of person.cells.entries()) {
                const td = node('td', null, `event-day-cell event-tone-${cell.tone}`), choose = node('button');
                choose.append(node('span',cell.calculated?'Служба':cell.event_type_name || cell.name || cell.label,'event-cell-type'));
                if(cell.code==='__pending__')choose.prepend(node('small','⚠ Завершення','event-cell-plan')); if(cell.subtype)choose.append(node('small',cell.subtype,'event-cell-subtype'));
                if(cell.mirage){td.classList.add('event-mirage');choose.prepend(node('small','Міраж','event-cell-plan'));}
                td.dataset.columnKey=`date:${model.buckets[index].start}:${model.buckets[index].end}`;
                EventUI.colour(td,cell);
                choose.type = 'button'; choose.title = cell.description; choose.setAttribute('aria-label', `${person.name}: ${cell.description}`); choose.addEventListener('click', () => select(person.id)); td.append(choose); tr.append(td);
            }
            rows.append(tr);
        }
        document.dispatchEvent(new Event('journal:rendered'));
    }
    function renderPerson() {
        const person = current(), index = model.people.findIndex(p => p.id === selected);
        document.querySelector('[data-journal-person]').textContent = person?.name || 'Оберіть військовослужбовця';
        document.querySelector('[data-journal-unit]').textContent = person ? `${person.unit} · ${person.rank}` : '';
        document.querySelector('[data-journal-event-count]').textContent = person ? `(${person.events.length})` : '';
        document.querySelector('[data-journal-prev]').disabled = index <= 0;
        document.querySelector('[data-journal-next]').disabled = index < 0 || index >= model.people.length - 1;
        all('[data-journal-add]').forEach(button => button.disabled = !person);
        const list = document.querySelector('[data-journal-events]'); list.replaceChildren();
        if (person && !person.events.length) list.append(node('p', 'У цьому періоді подій немає.', 'event-grid-hint'));
        for (const record of [...(person?.events || [])].reverse()) {
            const item = node('article', null, 'event-record-card'); item.dataset.journalEventId = record.event_id;
            const meta = model.types.find(kind => kind.id === record.event_type_id)?.presentation;
            if (meta) item.append(EventUI.badge({...meta,subtype:record.subtype_name,mirage:record.mirage}));
            const body = node('div', null, 'event-record-body'); body.append(node('strong',record.mirage?'Міраж · '+record.period:record.period));
            if(record.planned_end)body.append(node('p','Орієнтовно до '+record.planned_end.split('-').reverse().join('.')));
            body.append(node('p',record.completion_confirmed?'Завершення підтверджене':'Завершення не підтверджене'));
            for (const value of [record.subtype_name, record.purpose, record.location, record.note, record.event_status]) if (value) body.append(node('p', value));
            if (record.order_number || record.order_date) body.append(node('p', `Наказ: ${record.order_number || 'номер не зазначено'}${record.order_date ? ' · ' + record.order_date.split('-').reverse().join('.') : ''}`));
            const edit = node('button', '✎'); edit.type = 'button'; edit.title = 'Редагувати подію'; edit.setAttribute('aria-label', 'Редагувати подію'); edit.addEventListener('click', () => PersonEvents.open(person.id, person.name, {eventId: record.event_id}));
            const actions=node('div',null,'event-card-actions');actions.append(edit);const annul=node('button','Анулювати');annul.type='button';annul.className='btn btn-sm btn-outline-danger';annul.addEventListener('click',()=>PersonEvents.open(person.id,person.name,{annulId:record.event_id}));actions.append(annul);
            item.append(body, actions); list.append(item);
        }
        if(person)PersonEvents.renderArchive(person.annulled,list,record=>PersonEvents.open(person.id,person.name,{archiveId:record.event_id}));
        const summary = document.querySelector('[data-journal-summary]'), presence = document.querySelector('[data-journal-presence]'); summary.replaceChildren(); presence.replaceChildren();
        for (const entry of person?.summary || []) {
            const card = node('div',entry.calculated?'Служба (розрах.)':entry.label, `event-tone-${entry.tone}`);card.title=entry.name; card.append(node('strong', `${entry.days} дн.`)); summary.append(card);
            const line = node('div', null, 'event-presence-list'); line.append(EventUI.badge(entry), node('strong', `${entry.days} дн.`)); presence.append(line);
        }
        const short=person?.name.split(/\s+/)||[];document.querySelector('[data-journal-summary-title]').textContent=person?'Підсумок: '+[short[0],...short.slice(1).map(word=>word[0]+'.')].join(' '):'Підсумок: оберіть людину';
        document.querySelector('[data-journal-period]').textContent = `${model.options.start.split('-').reverse().join('.')} — ${model.options.end.split('-').reverse().join('.')}`;
    }
    all('[data-journal-add]').forEach(button => button.addEventListener('click', () => { const p = current(); if (p) PersonEvents.open(p.id, p.name, {create: true}); }));
    document.querySelector('[data-journal-prev]').addEventListener('click', () => { const i = model.people.findIndex(p => p.id === selected); if (i > 0) select(model.people[i-1].id); });
    document.querySelector('[data-journal-next]').addEventListener('click', () => { const i = model.people.findIndex(p => p.id === selected); if (i >= 0 && i < model.people.length - 1) select(model.people[i+1].id); });
    all('[data-journal-tab]').forEach(button => button.addEventListener('click', () => {
        all('[data-journal-tab]').forEach(tab => tab.setAttribute('aria-selected', String(tab === button)));
        document.querySelector('[data-journal-events-tab]').hidden = button.dataset.journalTab !== 'events';
        document.querySelector('[data-journal-presence-tab]').hidden = button.dataset.journalTab !== 'presence';
    }));
    all('[data-journal-sort]').forEach(button => button.addEventListener('click', () => {
        const form = document.querySelector('[data-journal-filters]'); form.elements.direction.value = model.options.sort === button.dataset.journalSort && model.options.direction === 'asc' ? 'desc' : 'asc'; form.elements.sort.value = button.dataset.journalSort; form.requestSubmit();
    }));
    document.querySelector('[data-journal-export]').addEventListener('click',()=>{
        const keys=[...document.querySelectorAll('.event-timeline thead th[data-column-key]')].filter(th=>!th.hidden).map(th=>th.dataset.columnKey);
        const labels={row_number:'№',name:'ПІБ',unit:'Підрозділ',position_number:'№ посади за штатом',position_short:'Коротка посада'};
        const dates=Object.fromEntries(model.buckets.map((bucket,index)=>[`date:${bucket.start}:${bucket.end}`,{index,label:bucket.period}]));
        EventUI.download([keys.map(key=>labels[key]||dates[key].label),...model.people.map((person,index)=>keys.map(key=>key==='row_number'?index+1:dates[key]?person.cells[dates[key].index].description:person[key]??''))],`events-${model.options.start}-${model.options.end}.csv`);
    });
    document.querySelector('[data-journal-filters]').addEventListener('submit', event => {
        const form = event.currentTarget, end = form.querySelector('[data-exact-date-for=end]') || form.elements.end;
        end.setCustomValidity('');
        let error = '';
        if (form.elements.start.value > form.elements.end.value) error = 'Завершення не може передувати початку.';
        else if ((Date.parse(form.elements.end.value+'T00:00:00Z')-Date.parse(form.elements.start.value+'T00:00:00Z'))/86400000 >= 366) error = 'Оберіть період не більше 366 днів.';
        if (error) { event.preventDefault(); end.setCustomValidity(error); form.reportValidity(); }
    });
    document.querySelector('[data-journal-filters]').addEventListener('input', event => { const end = event.currentTarget.querySelector('[data-exact-date-for=end]') || event.currentTarget.elements.end; if (['Завершення не може передувати початку.','Оберіть період не більше 366 днів.'].includes(end.validationMessage)) end.setCustomValidity(''); });
    document.addEventListener('person-events:saved', async () => {
        const token = ++generation;
        try {
            const response = await fetch('/events/data' + location.search, {cache: 'no-store'}), data = await response.json();
            if (!response.ok) throw Error(data.detail || 'Не вдалося оновити журнал.');
            if (token !== generation) return;
            model = data; renderRows(); select(model.people.some(p => p.id === selected) ? selected : model.people[0]?.id || null);
        } catch (error) { message.textContent = error.message; message.className = 'alert alert-warning'; }
    });
    all('[data-journal-sort]').forEach(button=>{const active=model.options.sort===button.dataset.journalSort;button.closest('th').setAttribute('aria-sort',active?(model.options.direction==='asc'?'ascending':'descending'):'none');});
    if(model.options.sort.startsWith('date:')){const parts=model.options.sort.split(':').slice(1).map(value=>value.split('-').reverse().join('.'));const caption=node('p','Сортування за станом у періоді '+parts.join(' — '),'event-filter-explanation');document.querySelector('[data-journal-filters]').after(caption);}
    renderRows(); JournalControls.initialise(model); const initial = Number(new URL(location.href).searchParams.get('person_id'));
    select(model.people.some(p => p.id === initial) ? initial : model.people[0]?.id || null, false);
})();

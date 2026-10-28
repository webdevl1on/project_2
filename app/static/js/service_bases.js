/* Optional directory suggestions never replace document wording silently. */
(function (root) {
    function activeKind(kind) { return ['mobilization', 'contract'].includes(kind) ? kind : ''; }
    function mayReplace(current, proposed, confirm) { return !current.trim() || current === proposed || confirm(); }
    if (typeof module === 'object' && module.exports) module.exports = { activeKind, mayReplace };
    if (!root.document) return;
    document.querySelectorAll('[data-service-basis-form]').forEach(form => {
        const kind = form.querySelector('[name="service_type"]');
        const sync = () => form.querySelectorAll('[data-basis-fields]').forEach(group => {
            group.hidden = group.dataset.basisFields !== activeKind(kind.value); group.disabled = group.hidden;
        });
        sync(); kind.addEventListener('change', sync);
        const select = form.querySelector('[name="tcc_office_id"]');
        const hint = form.querySelector('[data-tcc-hint]');
        const documentName = form.querySelector('[name="document_tcc_name"]');
        let generation = 0, options = new Map();
        const query = form.querySelector('[data-tcc-query]');
        query.addEventListener('input', () => { generation++; });
        for (const field of ['region', 'settlement']) form.elements[field].addEventListener('input', () => { generation++; });
        form.querySelector('[data-tcc-search]').addEventListener('click', async () => {
            const token = ++generation;
            const params = new URLSearchParams({q: query.value, region: form.elements.region.value, settlement: form.elements.settlement.value});
            try {
                const response = await fetch('/tcc/suggestions?' + params); const data = await response.json();
                if (token !== generation) return;
                if (!response.ok) throw new Error(data.detail || 'Помилка пошуку ТЦК.');
                // Keep an existing link even when it is inactive or outside current search results.
                const selected = select.selectedOptions[0], value = select.value;
                select.replaceChildren(new Option('Без довідникового посилання', ''));
                options = new Map(data.offices.map(office => [String(office.id), office]));
                if (value && !options.has(value)) select.add(new Option(selected.textContent, value));
                for (const office of data.offices) select.add(new Option([office.official_name, office.region, office.settlement].filter(Boolean).join(' · '), String(office.id)));
                select.value = value;
                hint.textContent = data.offices.length ? 'Оберіть підказку або залиште власне формулювання.' : 'Збігів немає. Можна зберегти власну назву без довідникового посилання.';
            } catch (error) { if (token === generation) hint.textContent = error.message; }
        });
        select.addEventListener('change', () => {
            const office = options.get(select.value); if (!office) return;
            if (mayReplace(documentName.value, office.official_name, () => root.confirm('Замінити введене формулювання назвою з довідника?'))) documentName.value = office.official_name;
            for (const field of ['region', 'settlement']) if (!form.elements[field].value) form.elements[field].value = office[field] || '';
            hint.textContent = 'Назву з документа можна виправити вручну. Розбіжність не блокує збереження.';
        });
    });
    if (document.querySelector('[data-service-basis-form]')) fetch('/tcc/locations').then(response => response.ok ? response.json() : {}).then(data => {
        for (const field of ['region', 'settlement']) for (const value of data[field] || []) document.querySelector(field === 'region' ? '#tcc-regions' : '#tcc-settlements').append(new Option(value, value));
    }).catch(() => {});
})(typeof window !== 'undefined' ? window : globalThis);

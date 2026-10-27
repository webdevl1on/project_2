/* Shared geographic entry: text remains authoritative when a lookup is absent. */
(() => {
    const root = document.querySelector('#person-geography');
    if (!root) return;
    const order = ['country','region','district','community','settlement','street'];
    const states = new WeakMap();
    function invalidate(form, kind) {
        order.slice(order.indexOf(kind)).forEach(key => {
            const input = form.elements[key];
            if (input && states.has(input)) {
                clearTimeout(states.get(input).timer);
                states.get(input).generation++;
            }
            const list = form.querySelector(`[data-geo-results="${key}"]`);
            if (list) list.replaceChildren();
            if (form.elements[key + '_id']) form.elements[key + '_id'].value = '';
        });
        form.querySelector('[data-geo-warning]').textContent = 'Компоненти змінено: довідникові посилання скинуто, введений текст збережено. Перевірте залежні поля; ручне збереження дозволено.';
    }
    root.addEventListener('input', event => {
        const input = event.target, kind = input.dataset.geoKind;
        if (!kind) return;
        const form = input.form;
        invalidate(form, kind);
        const state = states.get(input) || {generation:0};
        states.set(input, state);
        const generation = ++state.generation, query = input.value;
        if (query.trim().length < 2) return;
        state.timer = setTimeout(async () => {
            const params = new URLSearchParams({kind, q:query});
            for (const key of order.slice(0, order.indexOf(kind)).reverse()) {
                if (form.elements[key + '_id']?.value) { params.set('parent_id', form.elements[key + '_id'].value); break; }
            }
            try {
                const response = await fetch('/geography/search?' + params);
                if (!response.ok) throw new Error();
                const results = await response.json();
                if (state.generation !== generation || input.value !== query) return;
                const list = form.querySelector(`[data-geo-results="${kind}"]`);
                list.replaceChildren();
                results.forEach(unit => {
                    const button = document.createElement('button');
                    button.type = 'button'; button.className = 'list-group-item list-group-item-action';
                    button.textContent = [unit.name, unit.context].filter(Boolean).join(' — ');
                    button.addEventListener('click', () => {
                        invalidate(form, kind);
                        input.value = unit.name; form.elements[kind + '_id'].value = unit.id;
                        const typeInput = form.elements[kind + '_type'];
                        if (typeInput && unit.type && typeInput.value !== unit.type) {
                            if (!typeInput.value.trim() || window.confirm(`Замінити введений тип «${typeInput.value}» на довідниковий «${unit.type}»?`)) {
                                typeInput.value = unit.type;
                            }
                        }
                        list.replaceChildren();
                    });
                    list.append(button);
                });
            } catch (_) {
                if (state.generation === generation) form.querySelector('[data-geo-warning]').textContent = 'Пошук недоступний; ручне введення та збереження доступні.';
            }
        }, 250);
    });
    root.addEventListener('click', event => {
        if (!event.target.closest('[data-copy-registration]')) return;
        const source = root.querySelector('[data-block="registration"]');
        const target = event.target.closest('form');
        if ([...target.elements].some(input => !['revision','record_id'].includes(input.name) && input.value) && !window.confirm('Замінити введені компоненти фактичної адреси?')) return;
        order.forEach(kind => invalidate(target, kind));
        for (const input of source.elements) {
            if (input.name && !['revision','record_id'].includes(input.name) && target.elements[input.name]) target.elements[input.name].value = input.value;
        }
    });
    root.addEventListener('submit', async event => {
        const form = event.target.closest('[data-geo-form]');
        if (!form) return;
        event.preventDefault();
        const section = form.closest('[data-geo-block]'), button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
            const response = await fetch(form.action, {method:'POST', body:new FormData(form)});
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const updated = doc.querySelector(`[data-geo-block="${form.dataset.block}"]`);
            if (!updated) throw new Error();
            section.replaceWith(updated);
            root.querySelector('[data-geo-history]').replaceWith(doc.querySelector('[data-geo-history]'));
            updated.querySelector('[role="alert"]')?.focus();
        } catch (_) {
            form.querySelector('[data-geo-warning]').textContent = 'Не вдалося зберегти. Введені значення залишено; повторіть спробу.';
        } finally { button.disabled = false; }
    });
})();

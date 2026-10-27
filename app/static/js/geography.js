/* Shared geographic entry: text remains authoritative when a lookup is absent. */
(() => {
    const root = document.querySelector('#person-geography');
    if (!root) return;
    const order = ['country','region','district','community','settlement','street'];
    const states = new WeakMap();
    const fields = form => [...form.querySelectorAll('input:not([type="hidden"]), textarea, select')];
    function refresh(form) {
        for (const input of fields(form)) {
            let button = input.parentElement.querySelector('[data-geo-clear-field]');
            if (!button) {
                const wrapper = document.createElement('div');
                wrapper.className = 'position-relative';
                input.before(wrapper); wrapper.append(input);
                input.style.paddingRight = '3rem'; input.style.minHeight = '44px';
                button = document.createElement('button');
                button.type = 'button'; button.dataset.geoClearField = input.name;
                button.className = 'btn btn-link position-absolute top-0 end-0 text-secondary text-decoration-none';
                button.style.width = '44px'; button.style.height = '44px';
                button.textContent = '×';
                const label = input.labels?.[0]?.textContent.trim() || input.name;
                button.setAttribute('aria-label', `Очистити поле «${label}»`);
                wrapper.append(button);
            }
            button.hidden = !input.value; button.style.display = input.value ? '' : 'none';
        }
    }
    function clearError(form) {
        form.querySelector('[data-geo-client-error]')?.remove();
    }
    root.querySelectorAll('[data-geo-form]').forEach(refresh);
    root.addEventListener('change', event => {
        if (event.target.form?.matches('[data-geo-form]')) refresh(event.target.form);
    });
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
        if (input.form?.matches('[data-geo-form]')) { refresh(input.form); clearError(input.form); }
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
                        list.replaceChildren(); refresh(form);
                    });
                    list.append(button);
                });
            } catch (_) {
                if (state.generation === generation) form.querySelector('[data-geo-warning]').textContent = 'Пошук недоступний; ручне введення та збереження доступні.';
            }
        }, 250);
    });
    root.addEventListener('click', event => {
        const clearField = event.target.closest('[data-geo-clear-field]');
        const clearForm = event.target.closest('[data-geo-clear-form]');
        if (clearField || clearForm) {
            const form = (clearField || clearForm).closest('[data-geo-form]');
            if (clearForm) {
                if (fields(form).some(input => input.value.trim()) && !window.confirm('Очистити всі поля цієї форми? Незбережені зміни буде втрачено')) return;
                order.forEach(kind => invalidate(form, kind));
                fields(form).forEach(input => { input.value = ''; });
                fields(form)[0]?.focus();
            } else {
                const input = form.elements[clearField.dataset.geoClearField];
                input.value = '';
                if (input.dataset.geoKind) invalidate(form, input.dataset.geoKind);
                input.focus();
            }
            clearError(form); refresh(form); return;
        }
        if (!event.target.closest('[data-copy-registration]')) return;
        const source = root.querySelector('[data-block="registration"]');
        const target = event.target.closest('form');
        if ([...target.elements].some(input => !['revision','record_id'].includes(input.name) && input.value) && !window.confirm('Замінити введені компоненти фактичної адреси?')) return;
        order.forEach(kind => invalidate(target, kind));
        for (const input of source.elements) {
            if (input.name && !['revision','record_id'].includes(input.name) && target.elements[input.name]) target.elements[input.name].value = input.value;
        }
        clearError(target); refresh(target);
    });
    root.addEventListener('submit', async event => {
        const form = event.target.closest('[data-geo-form]');
        if (!form) return;
        event.preventDefault();
        clearError(form);
        if (!form.dataset.geoMeaningful.split(',').some(key => form.elements[key]?.value.trim())) {
            const error = document.createElement('div');
            error.className = 'alert alert-danger'; error.dataset.geoClientError = '';
            error.setAttribute('role', 'alert'); error.tabIndex = -1;
            error.textContent = form.dataset.geoEmptyMessage;
            form.prepend(error); form.closest('details').open = true; error.focus(); return;
        }
        const section = form.closest('[data-geo-block]'), button = form.querySelector('[type="submit"]');
        button.disabled = true;
        try {
            const response = await fetch(form.action, {method:'POST', body:new FormData(form)});
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const updated = doc.querySelector(`[data-geo-block="${form.dataset.block}"]`);
            if (!updated) throw new Error();
            section.replaceWith(updated);
            refresh(updated.querySelector('[data-geo-form]'));
            root.querySelector('[data-geo-history]').replaceWith(doc.querySelector('[data-geo-history]'));
            updated.querySelector('[role="alert"]')?.focus();
        } catch (_) {
            form.querySelector('[data-geo-warning]').textContent = 'Не вдалося зберегти. Введені значення залишено; повторіть спробу.';
        } finally { button.disabled = false; }
    });
})();

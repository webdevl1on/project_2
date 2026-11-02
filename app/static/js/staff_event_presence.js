(() => {
    'use strict';
    function syncQuickFilters() {
        const controller = globalThis.TableColumns?.controllers.get('person-positions'); if (!controller) return;
        const visible = controller.getLayout().visible;
        document.querySelectorAll('[data-staff-quick-filter]').forEach(select => {
            select.disabled = !visible.includes(select.dataset.staffQuickFilter);
            select.title = select.disabled ? 'Покажіть цю колонку, щоб застосувати її фільтр.' : '';
        });
    }
    document.addEventListener('DOMContentLoaded', syncQuickFilters);
    document.addEventListener('columnlayout:change', syncQuickFilters, true);
    document.querySelectorAll('[data-staff-quick-filter]').forEach(select => select.addEventListener('change', () => {
        const key = select.dataset.staffQuickFilter, url = new URL(location.href);
        url.searchParams.delete(key); url.searchParams.delete(key + '__contains');
        const order = (url.searchParams.get('filter_order') || '').split(',').filter(value => value && value !== key && value !== key + '__contains');
        if (select.value) { url.searchParams.set(key, select.value); order.push(key); }
        url.searchParams.set('filter_order', order.join(',')); location.assign(url);
    }));
    document.querySelector('[data-staff-compact]')?.addEventListener('click', () => {
        const controller = globalThis.TableColumns?.controllers.get('person-positions'); if (!controller) return;
        const visible = ['row_number','position_number','unit_short','name_short','rank','full_name','assignment','event_on_date'];
        const order = [...visible, ...controller.getLayout().order.filter(key => !visible.includes(key))];
        controller.state.widths = controller.model.widths({...controller.state.widths, position_number:85,unit_short:130,name_short:180,rank:145,full_name:220,assignment:280,event_on_date:165});
        controller.commitLayout({visible, order}); controller.storage.save(controller.state);
    });
    document.addEventListener('person-events:saved' , async event => {
        const pid = String(event.detail.personId);
        const cells = [...document.querySelectorAll('[data-event-presence-person]')].filter(cell => cell.dataset.eventPresencePerson === pid);
        if (!cells.length) return;
        try {
            const on = cells[0].dataset.eventPresenceOn;
            const response = await fetch('/events/presence?' + new URLSearchParams({person_id: pid, on}), {cache: 'no-store'});
            if (!response.ok) return;
            const state = await response.json();
            for (const cell of cells) { const badge = EventUI.badge(state); badge.dataset.columnValue = ''; cell.replaceChildren(badge); }
        } catch { /* The existing editor already reports success; reload can refresh the read view. */ }
    });
})();

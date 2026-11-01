const assert = require('node:assert/strict');
module.exports = async ({context, base}) => {
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const scenario = async (name, run) => { await run(); console.log(`PASS events: ${name}`); };
    const modal = page.locator('#person-events-modal'), form = modal.locator('[data-event-form]');
    const field = name => form.locator(`[name="${name}"]`);
    const cards = modal.locator('[data-event-id]');
    let catalog;
    const kind = code => String(catalog.types.find(t => t.code === code).id);
    const subtype = code => String(catalog.types.flatMap(t => t.subtypes).find(s => s.code === code).id);
    const listing = async pid => (await context.request.get(`${base}/persons/${pid}/events`)).json();
    async function open(pid) {
        await page.locator(`[data-events-open][data-person-id="${pid}"]`).click();
        await modal.locator('[data-event-new]:not([disabled])').waitFor();
    }
    async function fresh() {
        await modal.locator('[data-event-new]').click();
        await form.waitFor({state:'visible'});
    }
    async function save() {
        const response = page.waitForResponse(r => r.url().includes('/events') && r.request().method() === 'POST');
        await form.getByRole('button', {name:'Зберегти подію', exact:true}).click();
        return response;
    }
    try {
        await page.goto(base + '/person-positions'); catalog = await listing(1);
        await scenario('official-person buttons open an independent modal without touching assignments or cell selection', async () => {
            assert.equal(await page.locator('[data-events-open]').count(), 2);
            await open(1);
            assert.equal(await modal.locator('[data-events-person]').textContent().then(t=>t.includes('Альфа')), true);
            assert.equal(await page.locator('[data-assignment-editor]:visible').count(), 0);
            assert.equal(await page.locator('.cell-selected').count(), 0);
            await fresh(); assert.equal(await field('date_start').inputValue(), '');
            assert.equal(await field('date_end').inputValue(), '');
            assert.equal(await field('duration').inputValue(), '');
        });
        await scenario('dependent subtypes reset on type change; inactive dictionary entries are unavailable for new events', async () => {
            assert.equal(await field('event_type_id').locator(`option[value="${kind('DAY_OFF')}"]`).count(), 0);
            await field('event_type_id').selectOption(kind('VACATION'));
            assert.equal(await field('event_subtype_id').locator(`option[value="${subtype('VACATION_OTHER')}"]`).count(), 0);
            await field('event_subtype_id').selectOption(subtype('VACATION_ANNUAL'));
            await field('event_type_id').selectOption(kind('SERVICE'));
            assert.equal(await field('event_subtype_id').inputValue(), '');
            assert.equal(await field('event_subtype_id').locator('option').count(), 1);
        });
        await scenario('open creation has NULL end and duration, and displays the full period without a fabricated date', async () => {
            await field('event_type_id').selectOption(kind('VACATION'));
            await field('event_subtype_id').selectOption(subtype('VACATION_ANNUAL'));
            await field('date_start').fill('2026-10-01');
            await field('note').fill('<img src=x onerror="window.eventInjected=true">');
            assert.equal((await save()).status(), 200);
            await form.waitFor({state:'hidden'}); await cards.first().waitFor();
            assert.ok((await cards.first().textContent()).includes('01.10.2026 — по сьогодні'));
            const row = (await listing(1)).events[0];
            assert.equal(row.date_end, null); assert.equal(row.duration, null);
            assert.equal(await page.evaluate(()=>window.eventInjected), undefined);
        });
        await scenario('a later event atomically closes the previous day and recalculates its duration', async () => {
            await fresh(); await field('event_type_id').selectOption(kind('SERVICE')); await field('date_start').fill('2026-10-15');
            assert.equal((await save()).status(), 200); await form.waitFor({state:'hidden'});
            await page.waitForFunction(() => document.querySelectorAll('[data-event-id]').length === 2);
            const records = (await listing(1)).events;
            assert.equal(records[1].date_end, '2026-10-14'); assert.equal(records[1].duration, 14);
            assert.equal(records[0].date_end, null);
            assert.ok((await cards.nth(1).textContent()).includes('01.10.2026 — 14.10.2026'));
        });
        await scenario('client date errors and server overlaps preserve every entered value and the open editor', async () => {
            await fresh(); await field('event_type_id').selectOption(kind('SERVICE'));
            await field('date_start').fill('2026-10-05'); await field('date_end').fill('2026-10-04');
            await field('note').fill('Чернетка після помилки');
            const url = page.url();
            await form.getByRole('button', {name:'Зберегти подію', exact:true}).click();
            assert.equal(await field('date_end').getAttribute('aria-invalid'), 'true');
            assert.equal(await field('date_end').evaluate(e => e === document.activeElement), true);
            await field('date_end').fill('2026-10-08');
            assert.equal((await save()).status(), 409);
            await modal.locator('[data-events-conflicts] li').first().waitFor();
            assert.equal(await field('date_start').inputValue(), '2026-10-05');
            assert.equal(await field('date_end').inputValue(), '2026-10-08');
            assert.equal(await field('note').inputValue(), 'Чернетка після помилки');
            assert.equal(page.url(), url); assert.equal(await form.isVisible(), true);
            assert.equal((await listing(1)).events.length, 2);
        });
        await scenario('network refusal and list reload retain the draft; editing retains the event ID', async () => {
            await page.route('**/persons/1/events', route => route.request().method() === 'POST' ? route.abort('failed') : route.continue());
            await field('date_start').fill('2026-10-30'); await field('date_end').fill('2026-10-31');
            await form.getByRole('button', {name:'Зберегти подію', exact:true}).click();
            await modal.locator('[data-events-message]').filter({hasText:'Введені поля збережено'}).waitFor();
            await page.unroute('**/persons/1/events');
            await modal.locator('[data-events-reload]').click();
            assert.equal(await field('note').inputValue(), 'Чернетка після помилки');
            page.once('dialog', dialog => dialog.accept()); await modal.locator('[data-event-cancel]').click();
            const current = (await listing(1)).events[0];
            await modal.locator(`[data-event-edit="${current.event_id}"]`).click();
            await field('note').fill('Виправлена примітка');
            assert.equal((await save()).status(), 200); await form.waitFor({state:'hidden'});
            const changed = (await listing(1)).events[0];
            assert.equal(changed.event_id, current.event_id); assert.equal(changed.note, 'Виправлена примітка');
            assert.equal((await listing(1)).events.length, 2);
        });
        await scenario('historical inactive type and subtype remain readable and editable without becoming new choices', async () => {
            await modal.getByRole('button', {name:'Закрити',exact:true}).click();
            await modal.waitFor({state:'hidden'}); await open(2);
            const state = await listing(2), old = state.events.find(row => row.type_code === 'DAY_OFF');
            await modal.locator(`[data-event-edit="${old.event_id}"]`).click();
            assert.ok((await field('event_type_id').locator('option:checked').textContent()).includes('неактивний'));
            await field('note').fill('Уточнення архівної події');
            assert.equal((await save()).status(), 200); await form.waitFor({state:'hidden'});
            const archivedSub = state.events.find(row => row.event_subtype_id === Number(subtype('VACATION_OTHER')));
            await modal.locator(`[data-event-edit="${archivedSub.event_id}"]`).click();
            assert.ok((await field('event_subtype_id').locator('option:checked').textContent()).includes('неактивний'));
            assert.deepEqual(errors, []);
        });
    } finally { await page.close(); }
};

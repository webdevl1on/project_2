const assert = require('node:assert/strict');
module.exports = async ({context, base}) => {
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const picker = page.locator('[data-column-picker]');
    const table = page.locator('#person-positions');
    const header = key => table.locator(`th[data-column-key="${key}"]`);
    const choice = key => picker.locator(`[data-visibility-tree] [data-column-choice="${key}"]`);
    const cells = async key => (await table.locator(`tbody [data-column-key="${key}"] [data-column-value]`).allTextContents()).map(text => text.trim());
    const scenario = async (name, fn) => { await fn(); console.log(`PASS catalogue: ${name}`); };
    async function visibility(keys, visible = true) {
        await picker.locator('[data-column-toggle]').click();
        for (const key of keys) await choice(key).setChecked(visible);
        await picker.locator('[data-column-apply]').click();
    }
    try {
        await page.goto(base + '/person-positions');
        await page.evaluate(() => localStorage.clear()); await page.reload();
        await scenario('all configured fields have unique keyed cells, new groups are hidden by default', async () => {
            const keys = await table.locator('thead th').evaluateAll(nodes => nodes.map(node => node.dataset.columnKey));
            assert.equal(keys.length, 57); assert.equal(new Set(keys).size, 57);
            assert.equal(await table.locator('thead th:visible').count(), 12);
            assert.equal(await table.locator('tbody tr').count(), 3);
            for (const row of await table.locator('tbody tr').all()) {
                assert.deepEqual(await row.locator('td').evaluateAll(nodes => nodes.map(node => node.dataset.columnKey)), keys);
            }
            for (const key of ['tax_number', 'passport_number', 'service_type', 'name_created_at']) {
                assert.equal(await header(key).isVisible(), false);
            }
        });
        await scenario('related values, leading zeros, partial dates and vacancies are rendered correctly', async () => {
            await visibility(['tax_number', 'passport_number', 'passport_issued_date', 'service_type', 'service_position_date', 'name_created_at']);
            assert.deepEqual(await cells('tax_number'), ['0000000001', '0000000002', '-']);
            assert.deepEqual(await cells('passport_number'), ['000123', '000456', '-']);
            assert.deepEqual(await cells('passport_issued_date'), ['_._.2015', '20.06.2020', '-']);
            assert.deepEqual(await cells('service_type'), ['Контракт', '-', '-']);
            assert.deepEqual(await cells('service_position_date'), ['_._.2019', '-', '-']);
            assert.match((await cells('name_created_at'))[0], /\d{2}:\d{2}:\d{2}\.\d{6} UTC$/);
            assert.equal(await header('name_created_at').locator('[data-column-hide]').count(), 1);
            assert.equal(await header('name_created_at').locator('[data-filter-key]').count(), 0);
            await page.reload(); assert.equal(await header('passport_number').isVisible(), true);
        });
        await scenario('new scalar filter cascades, hidden filter clears, undo restores it', async () => {
            await header('passport_number').scrollIntoViewIfNeeded();
            await header('passport_number').locator('[data-bs-toggle=dropdown]').click();
            const menu = page.locator('[data-filter-key="passport_number"]');
            await menu.locator('input[value="000123"]').check();
            await Promise.all([page.waitForURL(url => url.searchParams.has('passport_number')), menu.locator('.apply-filter').click()]);
            assert.equal(await table.locator('tbody tr').count(), 1);
            await header('unit_short').scrollIntoViewIfNeeded();
            await header('unit_short').locator('[data-bs-toggle=dropdown]').click();
            assert.deepEqual(await page.locator('[data-filter-key="unit_short"] .filter-options input').evaluateAll(nodes => nodes.map(node => node.value)), ['Перший']);
            await page.keyboard.press('Escape');
            await visibility(['passport_number'], false);
            await page.waitForURL(url => !url.searchParams.has('passport_number'));
            assert.equal(await table.locator('tbody tr').count(), 3);
            await picker.locator('[data-table-back]').click();
            await page.waitForURL(url => url.searchParams.has('passport_number'));
            assert.equal(await header('passport_number').isVisible(), true);
            assert.equal(await table.locator('tbody tr').count(), 1);
        });
        await scenario('new date column uses shared range filter, exact/partial formatting and typed sort', async () => {
            await page.goto(base + '/person-positions');
            await header('passport_issued_date').scrollIntoViewIfNeeded();
            await header('passport_issued_date').locator('[data-bs-toggle=dropdown]').click();
            const menu = page.locator('[data-date-menu][data-date-column-key="passport_issued_date"]');
            await menu.locator('[data-date-mode]').selectOption('range');
            await menu.locator('[data-date-boundary="start"]').fill('2015-01-01');
            await menu.locator('[data-date-boundary="end"]').fill('2015-12-31');
            await Promise.all([page.waitForURL(url => url.searchParams.has('passport_issued_date')), menu.locator('[data-date-apply]').click()]);
            assert.deepEqual(await cells('passport_number'), ['000123']);
            await header('passport_issued_date').scrollIntoViewIfNeeded();
            await header('passport_issued_date').locator('[data-bs-toggle=dropdown]').click();
            await Promise.all([page.waitForURL(url => !url.searchParams.has('passport_issued_date')), menu.locator('[data-date-clear]').click()]);
            await header('passport_issued_date').scrollIntoViewIfNeeded();
            await header('passport_issued_date').locator('[data-bs-toggle=dropdown]').click();
            await Promise.all([page.waitForURL(url => url.searchParams.get('sort_by') === 'passport_issued_date'), menu.locator('[data-date-sort="asc"]').click()]);
            // Shared policy places complete dates before incomplete dates.
            assert.deepEqual(await cells('passport_number'), ['000456', '000123', '-']);
        });
        await scenario('old preset applies unchanged with newly added fields hidden', async () => {
            const legacy = {version:1, id:'legacy-catalogue', table_id:'person-positions', name:'Старий пресет',
                columns:['row_number','surname','position_number','rank_order_date','assignment']};
            await page.evaluate(preset => localStorage.setItem('project2:table-presets:person-positions', JSON.stringify({version:1,presets:[preset]})), legacy);
            await page.reload();
            await picker.locator('[data-preset-apply]').click();
            assert.deepEqual(await table.locator('thead th:visible').evaluateAll(nodes => nodes.map(node => node.dataset.columnKey)), legacy.columns);
            assert.equal(await header('passport_number').isVisible(), false);
            assert.equal(await picker.locator('[data-preset-warning]').isVisible(), false);
            const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('project2:table-presets:person-positions')).presets[0]);
            assert.deepEqual(saved, legacy);
            assert.deepEqual(errors, []);
        });
    } finally { await page.close(); }
};

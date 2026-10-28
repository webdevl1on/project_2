const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
module.exports = async ({context, base, adminToken}) => {
    await context.clearCookies();
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const scenario = async (name, check) => { await check(); console.log(`PASS service bases: ${name}`); };
    const submit = async form => {
        const request = page.waitForResponse(response => response.request().method() === 'POST' && response.url().includes('/service-bases'));
        await form.getByRole('button', {name:'Зберегти підставу', exact:true}).click();
        const response = await request; assert.equal(response.status(), 200);
        await page.waitForEvent('load');
    };
    const newBasis = () => page.locator('[data-new-basis]');
    const file = () => execFileSync(process.env.PYTHON || 'python3', ['-c',
        "from tests.test_service_bases import workbook,office\nimport sys\nsys.stdout.buffer.write(workbook([office(official_name='Імпортований ТЦК')]))"]);
    try {
        await scenario('TCC administration uses existing login and CSRF protection', async () => {
            assert.equal((await context.request.get(base+'/admin/tcc')).status(),401);
            assert.equal((await context.request.post(base+'/admin/tcc/new', {form:{official_name:'Заборонений'}})).status(),401);
            await page.goto(base+'/admin/login'); await page.locator('#token').fill(adminToken);
            await Promise.all([page.waitForURL(base+'/admin'), page.getByRole('button',{name:'Увійти',exact:true}).click()]);
            assert.ok(await page.getByRole('heading', {name:'Довідник ТЦК та СП'}).isVisible());
            assert.equal((await context.request.post(base+'/admin/tcc/new',{form:{official_name:'Без CSRF'}})).status(),403);
        });
        let officeId;
        await scenario('manual directory editing and repeatable Excel preview with confirmation', async () => {
            await page.goto(base+'/admin/tcc/new');
            await page.locator('[name="official_name"]').fill('Тестовий районний ТЦК та СП');
            await page.locator('[name="type"]').selectOption('district');
            await page.locator('[name="region"]').fill('Тестова область'); await page.locator('[name="settlement"]').fill('Тестове');
            await Promise.all([page.waitForURL(url=>url.pathname==='/admin/tcc'),page.getByRole('button',{name:'Зберегти ТЦК'}).click()]);
            officeId = Number((await page.locator('tbody tr').first().locator('td').first().innerText()).trim());
            await page.locator('[type="file"]').setInputFiles({name:'tcc.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:file()});
            await Promise.all([page.waitForURL('**/import/preview'),page.getByRole('button',{name:'Перевірити файл'}).click()]);
            assert.equal((await page.locator('[data-count="new"]').innerText()).trim(),'1');
            await page.locator('[name="reviewed"]').check();
            await Promise.all([page.waitForURL(url=>url.pathname==='/admin/tcc'),page.getByRole('button',{name:'Підтвердити імпорт ТЦК'}).click()]);
            await page.locator('[type="file"]').setInputFiles({name:'tcc.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:file()});
            await Promise.all([page.waitForURL('**/import/preview'),page.getByRole('button',{name:'Перевірити файл'}).click()]);
            assert.equal((await page.locator('[data-count="unchanged"]').innerText()).trim(),'1');
            assert.equal(await page.getByRole('button',{name:'Підтвердити імпорт ТЦК'}).count(),0);
        });
        let mobilizationId;
        await scenario('dictionary selection keeps manual document wording and allows mismatch', async () => {
            await page.goto(base+'/person_full_info/3#service-bases');
            await newBasis().locator('summary').click(); const form = newBasis().locator('form');
            await form.locator('[name="service_type"]').selectOption('mobilization');
            assert.equal(await form.locator('[name="contract_start_date"]').isVisible(),false);
            await form.locator('[name="mobilization_date"]').fill('2022-02-24');
            await form.locator('[name="document_tcc_name"]').fill('Точне історичне формулювання');
            await form.locator('[data-tcc-query]').fill('районний');
            await form.locator('[data-tcc-search]').click(); await form.locator(`[name="tcc_office_id"] option[value="${officeId}"]`).waitFor({state:'attached'});
            page.once('dialog',dialog=>dialog.dismiss());
            await form.locator('[name="tcc_office_id"]').selectOption(String(officeId));
            assert.equal(await form.locator('[name="document_tcc_name"]').inputValue(),'Точне історичне формулювання');
            await form.locator('[name="document_verified"]').check();
            await submit(form);
            const record = page.locator('[data-service-basis]').first(); mobilizationId=await record.getAttribute('data-service-basis');
            await record.locator('summary').click();
            assert.match(await record.innerText(),/Розбіжність/);
            assert.equal(await record.locator('[name="document_verified"]').isChecked(),true);
            await page.locator('[data-bs-target="#general"]').click();
            await page.getByText('Вид служби: за мобілізацією',{exact:true}).waitFor();
        });
        await scenario('current contract, independent dates and historical editing preserve drafts after server refusal', async () => {
            await page.locator('[data-bs-target="#service-bases"]').click(); await newBasis().locator('summary').click();
            let form=newBasis().locator('form'); await form.locator('[name="service_type"]').selectOption('contract');
            await form.locator('[name="contract_signed_date"]').fill('2025-01-01'); await form.locator('[name="contract_start_date"]').fill('2025-02-01');
            await form.locator('[name="contract_unit"]').fill('Тестова частина'); await form.locator('[name="is_current"]').check();
            await submit(form);
            const historical=page.locator(`[data-service-basis="${mobilizationId}"]`);
            assert.match(await historical.locator('summary').innerText(),/Історична/); await historical.locator('summary').click();
            form=historical.locator('form'); await form.locator('[name="document_tcc_name"]').fill('Виправлено за документом');
            // A stale revision simulates a real concurrent edit, without changing test-server business rules.
            await form.locator('[name="revision"]').evaluate(input=>input.value='0');
            await form.getByRole('button',{name:'Зберегти підставу'}).click(); await form.locator('[role="alert"]').waitFor();
            assert.match(await form.locator('[role="alert"]').innerText(),/вже змінено/);
            assert.equal(await form.locator('[name="document_tcc_name"]').inputValue(),'Виправлено за документом');
            assert.equal(await historical.evaluate(element=>element.open),true);
            await page.reload(); await page.locator('[data-bs-target="#general"]').click(); await page.getByText('Вид служби: за контрактом',{exact:true}).waitFor();
            await page.locator('[data-bs-target="#service-bases"]').click();
            const contract=page.locator('[data-service-basis]').first(); await contract.locator('summary').click();
            assert.equal(await contract.locator('[name="contract_signed_date"]').inputValue(),'2025-01-01');
            assert.equal(await contract.locator('[name="enlistment_order_date"]').inputValue(),'');
        });
        await scenario('directory rename does not rewrite a personal document and an unknown TCC can be saved', async () => {
            await page.goto(base+`/admin/tcc/${officeId}/edit`); await page.locator('[name="official_name"]').fill('Перейменований ТЦК');
            await page.locator('[name="is_active"]').uncheck();
            await Promise.all([page.waitForURL(url=>url.pathname==='/admin/tcc'),page.getByRole('button',{name:'Зберегти ТЦК'}).click()]);
            await page.goto(base+'/person_full_info/3#service-bases');
            const old=page.locator(`[data-service-basis="${mobilizationId}"]`); await old.locator('summary').click();
            assert.equal(await old.locator('[name="document_tcc_name"]').inputValue(),'Точне історичне формулювання');
            await newBasis().locator('summary').click(); const form=newBasis().locator('form');
            await form.locator('[name="service_type"]').selectOption('mobilization'); await form.locator('[name="document_tcc_name"]').fill('Установа лише в документі');
            await submit(form);
            // Input values are not textContent; identify the latest historical record by its input value.
            const inputs=page.locator('[data-service-basis] [name="document_tcc_name"]');
            assert.ok((await inputs.evaluateAll(elements=>elements.map(e=>e.value))).includes('Установа лише в документі'));
            assert.deepEqual(errors,[]);
        });
    } finally { await page.close(); }
};

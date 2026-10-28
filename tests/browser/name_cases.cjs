const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
module.exports = async ({context, base, adminToken}) => {
    const page = await context.newPage(), errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const scenario = async (name, check) => { await check(); console.log(`PASS name cases: ${name}`); };
    const cases = ['nominative','genitive','dative','accusative','instrumental','locative','vocative'];
    const csrf = async () => {
        const response = await context.request.get(base+'/admin');
        return (await response.text()).match(/name="csrf" value="([^"]+)"/)[1];
    };
    const lookup = async (word, sex='male') => (await context.request.get(base+'/name-dictionaries/lookup', {params:{kind:'name',sex,word}})).json();
    const group = () => page.locator('[data-name-part="name"]');
    async function blurName() {
        const response = page.waitForResponse(response => response.url().includes('/name-dictionaries/lookup') && new URL(response.url()).searchParams.get('kind') === 'name');
        await page.locator('#name').focus(); await page.locator('#name').blur(); await response;
        await page.waitForFunction(() => !document.querySelector('[data-name-part="name"] [data-case-status]').textContent.includes('ще не перевірено'));
    }
    function excel(duplicate=false) {
        const script = `from tests.test_name_cases import workbook,dictionary_data\nimport sys\nrows=[('names_male',dictionary_data(genitive='Імпортованого')),('names_male',dictionary_data(base='Іншеімя'))]\n${duplicate ? "rows.append(('names_male',dictionary_data(base='ТЕСТОСЛАВ')))" : ''}\nsys.stdout.buffer.write(workbook(rows))`;
        return execFileSync(process.env.PYTHON || 'python3', ['-c', script]);
    }
    let personUrl, personalUrl;
    try {
        await scenario('admin operations and downloads require login; GUI login enables a protected session', async () => {
            assert.equal((await context.request.post(base+'/admin/dictionaries/new',{form:{}})).status(),401);
            assert.equal((await context.request.get(base+'/admin/dictionaries/template.xlsx')).status(),401);
            await page.goto(base+'/admin/login'); await page.locator('#token').fill(adminToken);
            await Promise.all([page.waitForURL(base+'/admin'),page.getByRole('button',{name:'Увійти',exact:true}).click()]);
            assert.equal(await page.getByRole('heading',{name:'Словники відмінків'}).isVisible(),true);
            const cookie = (await context.cookies()).find(cookie=>cookie.name==='project2_admin');
            assert.equal(cookie.httpOnly,true); assert.equal(cookie.sameSite,'Strict');
            assert.equal((await context.request.post(base+'/admin/dictionaries/new',{form:{}})).status(),403);
        });
        await scenario('manual dictionary editing preserves spelling and distinguishes male and female forms', async () => {
            await page.goto(base+'/admin/dictionaries/new?kind=name');
            await page.locator('#sex').selectOption('male'); await page.locator('#base_form').fill('Тестослав');
            for(const key of cases) await page.locator('#'+key).fill(key==='genitive'?'Тестослава':'Тестослав');
            await page.locator('#is_verified').check();
            await Promise.all([page.waitForURL(url=>url.pathname==='/admin/dictionaries'),page.getByRole('button',{name:'Зберегти',exact:true}).click()]);
            const form = {kind:'name',sex:'female',base_form:'Тестослав',is_verified:'on',csrf:await csrf(),...Object.fromEntries(cases.map(key=>[key,key==='genitive'?'Тестославої':'Тестослав']))};
            assert.equal((await context.request.post(base+'/admin/dictionaries/new',{form})).status(),200);
            assert.equal((await lookup('ТЕСТОСЛАВ')).forms.genitive,'Тестослава');
            assert.equal((await lookup('Тестослав','female')).forms.genitive,'Тестославої');
            assert.equal((await lookup('Невідоме')).found,false);
        });
        await scenario('sex is the first step; known and unknown words give explicit results', async () => {
            await page.goto(base+'/persons/new');
            assert.equal(await page.locator('[data-person-details]').isVisible(),false);
            await page.locator('#sex_male').check();
            assert.equal(await page.locator('[data-person-details]').isVisible(),true);
            await page.locator('#surname').fill('Тестенко'); await page.locator('#name').fill('Тестослав');
            await blurName(); await group().locator('summary').click();
            await page.waitForFunction(()=>document.querySelector('#name_genitive').value==='Тестослава');
            await page.locator('#patronymic').fill('Тестович'); await page.locator('#patronymic').blur();
            await page.locator('[data-name-part="patronymic"] [data-case-status]').filter({hasText:'немає'}).waitFor();
            assert.equal(await page.locator('#patronymic_genitive').inputValue(),'');
        });
        await scenario('manual correction is never overwritten without confirmation', async () => {
            await page.locator('#name_genitive').fill('Особистого'); await blurName();
            assert.equal(await page.locator('#name_genitive').inputValue(),'Особистого');
            const button = group().locator('[data-use-dictionary]'); await button.waitFor({state:'visible'});
            page.once('dialog',dialog=>dialog.dismiss()); await button.click();
            assert.equal(await page.locator('#name_genitive').inputValue(),'Особистого');
            page.once('dialog',dialog=>dialog.accept()); await button.click();
            assert.equal(await page.locator('#name_genitive').inputValue(),'Тестослава');
        });
        await scenario('word and sex changes show stale forms and require clear or explicit review', async () => {
            await page.locator('#name').fill('Новеімя');
            assert.equal(await group().locator('[data-stale-actions]').isVisible(),true);
            assert.equal(await page.locator('#name').evaluate(input=>input.checkValidity()),false);
            assert.equal(await page.locator('#name_genitive').inputValue(),'Тестослава');
            await group().locator('[data-clear-cases]').click();
            assert.equal(await page.locator('#name_genitive').inputValue(),'');
            await page.locator('#name').fill('Тестослав'); await blurName();
            await page.waitForFunction(()=>document.querySelector('#name_genitive').value==='Тестослава');
            await page.locator('#sex_female').check();
            assert.equal(await group().locator('[data-stale-actions]').isVisible(),true);
            await group().locator('[data-clear-cases]').click(); await blurName();
            await page.waitForFunction(()=>document.querySelector('#name_genitive').value==='Тестославої');
            await page.locator('#sex_male').check(); await group().locator('[data-clear-cases]').click(); await blurName();
            await page.waitForFunction(()=>document.querySelector('#name_genitive').value==='Тестослава');
        });
        await scenario('server validation preserves all entered cases, sex, rank and partial birth date', async () => {
            await page.locator('#name_genitive').fill('Особистого');
            await page.locator('#tax_number').fill('0000000001');
            await page.locator('[name="birth_month"]').fill('3'); await page.locator('[name="birth_year"]').fill('1993');
            await page.locator('#rank_id').selectOption('1');
            await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Зберегти людину'}).click()]);
            await page.locator('[data-form-error]').filter({hasText:'РНОКПП'}).waitFor();
            assert.equal(await page.locator('#name_genitive').inputValue(),'Особистого');
            assert.equal(await page.locator('#sex_male').isChecked(),true);
            assert.equal(await page.locator('#rank_id').inputValue(),'1');
            assert.equal(await page.locator('[name="birth_month"]').inputValue(),'3');
            assert.equal(await page.locator('[name="birth_day"]').inputValue(),'');
            await page.locator('#tax_number').fill('9999999999');
            await Promise.all([page.waitForURL(/\/persons\/\d+\/created/),page.getByRole('button',{name:'Зберегти людину'}).click()]);
            assert.equal(await page.getByRole('link',{name:'Повернутися до списку людей'}).isVisible(),true);
            personUrl=await page.getByRole('link',{name:'Перейти до повної анкети'}).getAttribute('href');
        });
        await scenario('created person has a rank and personal cases can be corrected by name history record', async () => {
            await page.goto(base+personUrl);
            assert.match(await page.locator('body').innerText(),/Солдат|солдат/);
            await page.locator('[data-bs-target="#names"]').click();
            personalUrl=await page.getByRole('link',{name:'Відмінки',exact:true}).getAttribute('href');
            await page.goto(base+personalUrl);
            await group().locator('summary').click();
            assert.equal(await page.locator('#name_genitive').inputValue(),'Особистого');
            await page.locator('#name_dative').fill('Особистому');
            await Promise.all([page.waitForURL(base+personUrl),page.getByRole('button',{name:'Зберегти персональні форми'}).click()]);
            assert.equal((await lookup('Тестослав')).forms.genitive,'Тестослава');
        });
        await scenario('Excel add-only preview and confirmation do not overwrite an existing entry', async () => {
            await page.goto(base+'/admin');
            await page.locator('#file').setInputFiles({name:'names.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:excel()});
            await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Перевірити файл'}).click()]);
            assert.equal(await page.locator('[data-count="new"]').innerText(),'1');
            assert.equal(await page.locator('[data-count="skipped"]').innerText(),'1');
            assert.equal((await lookup('Іншеімя')).found,false);
            await page.locator('#reviewed').check();
            const token=await page.locator('[name="token"]').inputValue(), csrfValue=await page.locator('[name="csrf"]').inputValue();
            await Promise.all([page.waitForURL(url=>url.pathname==='/admin'),page.getByRole('button',{name:'Підтвердити імпорт'}).click()]);
            assert.equal((await lookup('Тестослав')).forms.genitive,'Тестослава');
            assert.equal((await lookup('Іншеімя')).found,true);
            assert.equal((await context.request.post(base+'/admin/dictionaries/import/confirm',{form:{token,csrf:csrfValue,reviewed:'true'}})).status(),409);
        });
        await scenario('Excel updates require separate confirmation and preserve personal snapshots', async () => {
            await page.goto(base+'/admin'); await page.locator('#mode').selectOption('update');
            await page.locator('#file').setInputFiles({name:'names.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:excel()});
            await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Перевірити файл'}).click()]);
            assert.equal(await page.locator('[data-count="updated"]').innerText(),'1');
            await page.locator('#reviewed').check();
            const token=await page.locator('[name="token"]').inputValue(), csrfValue=await page.locator('[name="csrf"]').inputValue();
            assert.equal((await context.request.post(base+'/admin/dictionaries/import/confirm',{form:{token,csrf:csrfValue,reviewed:'true'}})).status(),409);
            await page.locator('#confirm_updates').check();
            await Promise.all([page.waitForURL(url=>url.pathname==='/admin'),page.getByRole('button',{name:'Підтвердити імпорт'}).click()]);
            assert.equal((await lookup('Тестослав')).forms.genitive,'Імпортованого');
            await page.goto(base+personalUrl); await group().locator('summary').click();
            assert.equal(await page.locator('#name_genitive').inputValue(),'Особистого');
            assert.equal(await page.locator('#name_dative').inputValue(),'Особистому');
        });
        await scenario('duplicate Excel rows prevent import; logout removes administrative access', async () => {
            await page.goto(base+'/admin');
            await page.locator('#file').setInputFiles({name:'duplicate.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:excel(true)});
            await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Перевірити файл'}).click()]);
            assert.equal(await page.locator('[data-count="errors"]').innerText(),'1');
            assert.equal(await page.getByRole('button',{name:'Підтвердити імпорт'}).count(),0);
            assert.match(await page.locator('body').innerText(),/names_male, рядок 5/);
            await page.goto(base+'/admin');
            await Promise.all([page.waitForURL(base+'/admin/login'),page.getByRole('button',{name:'Вийти з адміністрування'}).click()]);
            assert.equal((await context.request.post(base+'/admin/dictionaries/new',{form:{}})).status(),401);
            assert.deepEqual(errors,[]);
        });
    } finally { await page.close(); }
};

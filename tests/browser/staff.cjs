const assert=require('node:assert/strict');
const path=require('node:path');
module.exports=async({context,base})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.setViewportSize({width:1500,height:1200});
    const table=page.locator('#person-positions');
    const row=number=>table.locator('tbody tr').filter({has:page.locator('[data-column-key="position_number"] [data-column-value]',{hasText:String(number)})});
    const confirm=page.locator('#staff-assignment-confirm');
    const scenario=async(name,fn)=>{await fn();console.log(`PASS staff: ${name}`);};
    async function pick(number,person){
        await row(number).locator('[data-person-label]').click();
        await row(number).locator(`[data-person-option="${person}"]`).click();
    }
    try{
        await page.goto(base+'/person-positions');await page.evaluate(()=>localStorage.clear());await page.reload();
        await scenario('three-line selector, free first, partial birthday search and name search',async()=>{
            await row(30).locator('[data-person-label]').click();
            const picker=row(30).locator('[data-person-picker]');
            const options=picker.locator('[data-person-option]:not([data-person-option=""])');
            assert.equal(await options.first().getAttribute('data-person-option'),'3');
            assert.match(await options.first().innerText(),/Гамма Тест/);
            assert.match(await options.first().innerText(),/Солдат · 28.02.2001/);
            assert.match(await options.first().innerText(),/Вільний/);
            assert.match(await picker.locator('[data-person-option="1"]').innerText(),/Призначений · посада № 10/);
            assert.ok(!(await picker.innerText()).includes('(ID:'));
            await picker.locator('.person-search').fill('15._.1993');
            assert.equal(await picker.locator('[data-person-option="2"]').isVisible(),true);
            assert.equal(await picker.locator('[data-person-option="1"]').isVisible(),false);
            await picker.locator('.person-search').fill('аЛьФа');
            assert.equal(await picker.locator('[data-person-option="1"]').isVisible(),true);
            await page.keyboard.press('Escape');
        });
        await scenario('occupied target refuses replacement without changing source',async()=>{
            await pick(20,'1');
            await row(20).locator('[data-assignment-status]').filter({hasText:'зайнята'}).waitFor();
            assert.equal(await confirm.isVisible(),false);
            await page.reload();assert.equal(await row(10).locator('[data-person-value]').inputValue(),'1');
            assert.equal(await row(20).locator('[data-person-value]').inputValue(),'2');
        });
        await scenario('cancel transfer leaves DB unchanged, confirmed transfer updates both positions',async()=>{
            await pick(30,'1');await confirm.waitFor({state:'visible'});
            assert.match(await confirm.innerText(),/посаду № 10/);assert.match(await confirm.innerText(),/посаду № 30/);
            await confirm.getByRole('button',{name:'Ні',exact:true}).click();
            await page.reload();assert.equal(await row(10).locator('[data-person-value]').inputValue(),'1');
            assert.equal(await row(30).locator('[data-person-value]').inputValue(),'');
            await pick(30,'1');await confirm.waitFor({state:'visible'});
            await Promise.all([page.waitForNavigation(),confirm.locator('[data-assignment-confirm-yes]').click()]);
            assert.equal(await row(10).locator('[data-person-value]').inputValue(),'');
            assert.equal(await row(30).locator('[data-person-value]').inputValue(),'1');
            await row(30).locator('form [type=submit]').click();
            await row(30).locator('[data-assignment-status]').filter({hasText:'уже призначений'}).waitFor();
            await pick(10,'3');
            await Promise.all([page.waitForNavigation(),row(10).locator('form [type=submit]').click()]);
            assert.equal(await row(10).locator('[data-person-value]').inputValue(),'3');
        });
        await scenario('history shows retained source and explicit atomic version closure',async()=>{
            await page.getByRole('link',{name:'Версії та історія призначень'}).click();
            assert.ok((await page.locator('body').innerText()).includes('Історичні призначення'));
            assert.equal(await page.locator('form[action$="/correct"] [name="assigned_from"]').count(),4);
            const section=page.locator('details').filter({has:page.locator('summary',{hasText:'Явно закрити'})});
            await section.locator('summary').click();
            const today=await page.evaluate(()=>new Date().toLocaleDateString('en-CA',{timeZone:'Europe/Kyiv'}));
            await section.locator('[name="valid_to"]').fill(today);
            await section.locator('[name="confirmed"]').check();
            await Promise.all([page.waitForNavigation(),section.getByRole('button',{name:'Закрити версію'}).click()]);
            assert.ok((await page.locator('body').innerText()).includes('Версію та всі її відкриті призначення завершено'));
        });
        await scenario('Excel upload previews only positions, confirmation imports a vacant version; replay conflicts',async()=>{
            await page.goto(base+'/person-positions');
            await page.getByRole('button',{name:'Завантажити штатну структуру',exact:true}).click();
            const modal=page.locator('#staff-import-modal');
            await modal.locator('[name="file"]').setInputFiles(path.resolve(__dirname,'../../reference_data.xlsx'));
            await modal.locator('[name="name"]').fill('Браузерна архівна версія');
            // Earlier than the explicit synthetic regression version; no overlap.
            await modal.locator('[name="valid_from"]').fill('1999-01-01');await modal.locator('[name="valid_to"]').fill('1999-12-31');
            await Promise.all([page.waitForNavigation(),modal.getByRole('button',{name:'Перевірити файл'}).click()]);
            assert.match(await page.locator('body').innerText(),/Кількість посад/);
            assert.equal(await page.getByRole('button',{name:'Підтвердити завантаження'}).count(),1);
            const token=await page.locator('[name="token"]').inputValue();
            await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Підтвердити завантаження'}).click()]);
            assert.equal(await table.locator('tbody tr').count(),10);
            assert.ok((await page.locator('body').innerText()).includes('Усі посади вакантні'));
            assert.deepEqual(await table.locator('[data-person-value]').evaluateAll(nodes=>nodes.map(node=>node.value)),Array(10).fill(''));
            await page.locator('#position-filters [name="version_id"]').selectOption('1');
            assert.equal(await page.locator('#position-filters [name="as_of"]').inputValue(),'2000-01-01');
            const repeat=await page.request.post(base+'/staff/import/confirm',{form:{token}});
            assert.equal(repeat.status(),409);
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

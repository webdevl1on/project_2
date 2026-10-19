const assert = require('node:assert/strict');
module.exports = async ({context,base}) => {
    const page=await context.newPage(), errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    async function scenario(name,fn){await fn();console.log(`PASS domain dates: ${name}`);}
    const picker=page.locator('[data-column-picker]');
    const table=page.locator('#person-positions');
    const header=key=>table.locator(`th[data-column-key="${key}"]`);
    const menu=key=>page.locator(`[data-date-menu][data-date-column-key="${key}"]`);
    try{
        await scenario('rank modal validates partial date, persists it and refines the same record',async()=>{
            await page.goto(base+'/person_full_info/1');
            await page.locator('[data-bs-target="#ranks"]').click();
            await page.locator('#ranks [data-bs-target^="#editRankModal"]').click();
            let modal=page.locator('.modal.show'); await modal.waitFor({state:'visible'});
            assert.equal(await modal.locator('[name="created_at"], [name="updated_at"]').count(),0);
            await modal.locator('[name="rank_order_day"]').fill('31');
            await modal.locator('[name="rank_order_month"]').fill('2');
            await modal.locator('[name="rank_order_year"]').fill('1995');
            assert.equal(await modal.locator('[name="rank_order_day"]').evaluate(node=>node.checkValidity()),false);
            await modal.locator('[name="rank_order_day"]').fill('');
            await modal.locator('[name="rank_order_month"]').fill('3');
            const action=await modal.locator('form').getAttribute('action');
            await Promise.all([page.waitForNavigation(),modal.locator('[type="submit"]').click()]);
            await page.locator('[data-bs-target="#ranks"]').click();
            assert.ok((await page.locator('#ranks').innerText()).includes('_.03.1995'));
            assert.equal(await page.locator('#ranks tbody tr').count(),1);
            await page.locator('#ranks [data-bs-target^="#editRankModal"]').click();
            modal=page.locator('.modal.show'); await modal.waitFor({state:'visible'});
            assert.equal(await modal.locator('form').getAttribute('action'),action);
            await modal.locator('[name="rank_order_day"]').fill('15');
            await Promise.all([page.waitForNavigation(),modal.locator('[type="submit"]').click()]);
            await page.locator('[data-bs-target="#ranks"]').click();
            assert.ok((await page.locator('#ranks').innerText()).includes('15.03.1995'));
            assert.equal(await page.locator('#ranks tbody tr').count(),1);
            // Keep one partial and one incompatible exact date for SQL/filter checks.
            const first=await page.request.post(base+action,{form:{rank_id:'1',rank_order_day:'',rank_order_month:'3',rank_order_year:'1995'},maxRedirects:0});
            assert.equal(first.status(),303);
            const second=await page.request.post(base+'/person_ranks/2/update',{form:{rank_id:'1',rank_order_day:'15',rank_order_month:'4',rank_order_year:'1996'},maxRedirects:0});
            assert.equal(second.status(),303);
        });
        await scenario('two date columns share cascading filters but store separate priorities',async()=>{
            await page.goto(base+'/person-positions'); await page.evaluate(()=>localStorage.clear()); await page.reload();
            assert.equal(await header('rank_order_date').isVisible(),false);
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="rank_order_date"]').check();
            await picker.locator('[data-column-apply]').click();
            await header('birth_date').locator('[data-bs-toggle="dropdown"]').click();
            await menu('birth_date').locator('[data-date-choices="years"] input[value="1993"]').check();
            await Promise.all([page.waitForNavigation(),menu('birth_date').locator('[data-date-apply]').click()]);
            await header('rank_order_date').locator('[data-bs-toggle="dropdown"]').click();
            const rankMenu=menu('rank_order_date');
            await rankMenu.locator('[data-date-mode]').selectOption('range');
            await rankMenu.locator('[data-date-boundary="start"]').fill('1995-03-10');
            await rankMenu.locator('[data-date-boundary="end"]').fill('1995-03-20');
            await Promise.all([page.waitForNavigation(),rankMenu.locator('[data-date-apply]').click()]);
            assert.equal(await table.locator('tbody tr').count(),1);
            assert.equal((await table.locator('tbody [data-column-key="rank_order_date"]').innerText()).trim(),'_.03.1995');
            assert.equal(new URL(page.url()).searchParams.get('filter_order'),'birth_date,rank_order_date');
            await header('rank_order_date').locator('[data-bs-toggle="dropdown"]').click();
            await rankMenu.locator('[data-date-priority-part="year"] [data-date-move="1"]').click();
            await Promise.all([page.waitForNavigation(),rankMenu.locator('[data-date-sort="desc"]').click()]);
            const priorities=await page.evaluate(()=>['birth_date','rank_order_date'].map(key=>JSON.parse(localStorage.getItem(`project2:date-priority:person-positions:${key}`)).priority));
            assert.deepEqual(priorities,[['year','month','day'],['month','year','day']]);
            await page.reload(); assert.equal(await table.locator('tbody tr').count(),1);
        });
        await scenario('hiding order date removes only its filter, undo/redo and browser traversal work',async()=>{
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="rank_order_date"]').uncheck();
            await Promise.all([page.waitForURL(url=>!url.searchParams.has('rank_order_date')),picker.locator('[data-column-apply]').click()]);
            assert.equal(await table.locator('tbody tr').count(),2);
            assert.ok(new URL(page.url()).searchParams.has('birth_date'));
            await picker.locator('[data-table-back]').click(); await page.waitForURL(url=>url.searchParams.has('rank_order_date'));
            assert.equal(await header('rank_order_date').isVisible(),true); assert.equal(await table.locator('tbody tr').count(),1);
            await picker.locator('[data-table-forward]').click(); await page.waitForURL(url=>!url.searchParams.has('rank_order_date'));
            await page.goBack(); await page.waitForURL(url=>url.searchParams.has('rank_order_date'));
            assert.equal(await header('rank_order_date').isVisible(),true);
            assert.deepEqual(errors,[]);
        });
    } finally{await page.close();}
};

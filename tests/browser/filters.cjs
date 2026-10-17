const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const picker=page.locator('[data-column-picker]'),table=page.locator('#person-positions');
    const values=async()=>(await table.locator('tbody [data-column-key="position_number"]').allTextContents()).map(s=>s.trim());
    const query='?unit_short=Перший&name_short=Водій&name_short=Медик&filter_order=unit_short,name_short&sort_by=position_number&direction=desc&occupancy=all&extra=keep';
    async function change(key,visible){
        await picker.locator('[data-column-toggle]').click();
        await picker.locator(`[data-visibility-tree] [data-column-choice="${key}"]`).setChecked(visible);
        await picker.locator('[data-column-apply]').click();
    }
    async function scenario(name,fn){await fn();console.log(`PASS filters: ${name}`);}
    try{
        await page.goto(base+'/person-positions');await page.evaluate(()=>localStorage.clear());
        await page.goto(base+'/person-positions'+query);
        await scenario('checkbox hiding removes its actual SQL filter and keeps all other query parameters',async()=>{
            assert.deepEqual(await values(),['10']);
            await change('unit_short',false);
            await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.deepEqual(await values(),['30','10']);
            const url=new URL(page.url());
            assert.deepEqual(url.searchParams.getAll('name_short'),['Водій','Медик']);
            assert.equal(url.searchParams.get('filter_order'),'name_short');
            assert.equal(url.searchParams.get('direction'),'desc');assert.equal(url.searchParams.get('extra'),'keep');
            assert.equal(await table.locator('th[data-column-key="unit_short"]').isVisible(),false);
        });
        await scenario('reload and direct links cannot reactivate hidden filters or loop',async()=>{
            let requests=0;const listener=r=>{if(r.isNavigationRequest()&&r.url().includes('/person-positions'))requests++;};
            page.on('request',listener);
            await page.reload();assert.deepEqual(await values(),['30','10']);
            requests=0;
            await page.goto(base+'/person-positions'+query);
            await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.deepEqual(await values(),['30','10']);assert.ok(requests<=2);
            page.off('request',listener);
        });
        await scenario('applying a preset removes only hidden filters and preserves cascade behaviour',async()=>{
            await picker.locator('.column-toolbar > [data-preset-create]').click();
            const modal=picker.locator('[data-preset-save-modal]');
            await modal.locator('[data-preset-name]').fill('Без підрозділу');
            await modal.locator('[type=submit]').click();await modal.waitFor({state:'hidden'});
            await change('unit_short',true);
            await table.locator('th[data-column-key="unit_short"] [data-bs-toggle=dropdown]').click();
            const menu=page.locator('[data-filter-key="unit_short"]');await menu.locator('input[value="Перший"]').check();
            await Promise.all([page.waitForURL(url=>url.searchParams.has('unit_short')),menu.locator('.apply-filter').click()]);
            assert.deepEqual(await values(),['10']);
            await picker.locator('[data-preset-apply]').click();
            await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.deepEqual(await values(),['30','10']);
            await table.locator('th[data-column-key="name_short"] [data-bs-toggle=dropdown]').click();
            const options=await page.locator('[data-filter-key="name_short"] .filter-options input').evaluateAll(nodes=>nodes.map(n=>n.value));
            assert.deepEqual(new Set(options),new Set(['Водій','Стрілець','Медик']));
            await page.keyboard.press('Escape');
            await table.locator('th[data-column-key="position_number"] .position-column-heading > a').click();
            await page.waitForURL(url=>url.searchParams.get('direction')==='asc');
            assert.deepEqual(await values(),['10','30']);
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

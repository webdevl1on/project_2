const assert = require('node:assert/strict');
module.exports = async ({context,base}) => {
    const page = await context.newPage(), errors = [];
    page.on('pageerror',error=>errors.push(error.message));
    const table=page.locator('#person-positions'), picker=page.locator('[data-column-picker]');
    const menu=page.locator('[data-date-menu][data-date-column-key="birth_date"]');
    const header=table.locator('th[data-column-key="birth_date"]');
    const open=()=>header.locator('[data-bs-toggle="dropdown"]').click();
    const count=()=>table.locator('tbody tr').count();
    async function scenario(name,fn){await fn();console.log(`PASS dates: ${name}`);}
    async function apply(){await Promise.all([page.waitForNavigation(),menu.locator('[data-date-apply]').click()]);}
    try {
        await page.goto(base+'/person-positions'); await page.evaluate(()=>localStorage.clear()); await page.reload();
        await scenario('range possible match includes partial dates and excludes unassigned positions',async()=>{
            assert.equal(await count(),3);
            assert.deepEqual((await table.locator('tbody [data-column-key="birth_date"]').allTextContents()).map(t=>t.trim()),['15.03.1993','15._.1993','—']);
            await open(); await menu.locator('[data-date-mode]').selectOption('range');
            await menu.locator('[data-date-boundary="start"]').fill('1993-03-10');
            await menu.locator('[data-date-boundary="end"]').fill('1993-03-20'); await apply();
            assert.equal(await count(),2); assert.equal(new URL(page.url()).searchParams.get('filter_order'),'birth_date');
        });
        await scenario('incomplete-only and cancel preserve applied data',async()=>{
            const before=page.url(); await open(); await menu.locator('[data-date-incomplete]').check();
            await menu.locator('[data-date-cancel]').click(); assert.equal(page.url(),before);
            await open(); assert.equal(await menu.locator('[data-date-incomplete]').isChecked(),false);
            await menu.locator('[data-date-incomplete]').check(); await apply(); assert.equal(await count(),1);
            assert.equal((await table.locator('tbody [data-column-key="birth_date"]').innerText()).trim(),'15._.1993');
        });
        await scenario('hiding a date removes its actual URL filter and undo/redo restore it',async()=>{
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="birth_date"]').uncheck();
            await Promise.all([page.waitForURL(url=>!url.searchParams.has('birth_date')),picker.locator('[data-column-apply]').click()]);
            assert.equal(await count(),3); assert.equal(await header.isVisible(),false);
            await picker.locator('[data-table-back]').click(); await page.waitForURL(url=>url.searchParams.has('birth_date'));
            assert.equal(await header.isVisible(),true); assert.equal(await count(),1);
            await picker.locator('[data-table-forward]').click(); await page.waitForURL(url=>!url.searchParams.has('birth_date'));
            await page.reload(); assert.equal(await count(),3); assert.equal(await header.isVisible(),false);
            await picker.locator('[data-table-back]').click(); await page.waitForURL(url=>url.searchParams.has('birth_date'));
        });
        await scenario('priority arrows persist separately from presets and filters',async()=>{
            await open();
            assert.equal(await menu.locator('[data-date-priority-part="year"] [data-date-move="-1"]').isDisabled(),true);
            await menu.locator('[data-date-priority-part="year"] [data-date-move="1"]').click();
            await Promise.all([page.waitForNavigation(),menu.locator('[data-date-sort="desc"]').click()]);
            const url=new URL(page.url()); assert.equal(url.searchParams.get('birth_date_priority'),'month,year,day');
            assert.equal(url.searchParams.get('sort_by'),'birth_date'); assert.ok(url.searchParams.has('birth_date'));
            await page.reload(); await open();
            assert.deepEqual(await menu.locator('[data-date-priority-part]').evaluateAll(nodes=>nodes.map(n=>n.dataset.datePriorityPart)),['month','year','day']);
            assert.deepEqual(await page.evaluate(()=>JSON.parse(localStorage.getItem('project2:date-priority:person-positions:birth_date')).priority),['month','year','day']);
            await menu.locator('[data-date-cancel]').click();
        });
        await scenario('components, searched years and cascade remain active together',async()=>{
            await open(); await menu.locator('[data-date-mode]').selectOption('parts');
            await menu.locator('[data-date-search="years"]').fill('1993');
            await menu.locator('[data-date-choices="years"] input[value="1993"]').check();
            await apply(); assert.equal(await count(),1); // incomplete-only remains active
            await table.locator('th[data-column-key="unit_short"] [data-bs-toggle="dropdown"]').click();
            const unit=page.locator('[data-filter-key="unit_short"]');
            await unit.locator('input[value="Перший"]').check();
            await Promise.all([page.waitForNavigation(),unit.locator('.apply-filter').click()]);
            assert.equal(await count(),1); assert.equal(new URL(page.url()).searchParams.get('filter_order'),'birth_date,unit_short');
            await open(); await Promise.all([page.waitForNavigation(),menu.locator('[data-date-clear]').click()]);
            assert.equal(await count(),2); assert.equal(new URL(page.url()).searchParams.get('unit_short'),'Перший');
            assert.equal(new URL(page.url()).searchParams.get('filter_order'),'unit_short');
        });
        await scenario('preset hiding a date clears its filter and undo restores both',async()=>{
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="birth_date"]').uncheck();
            await picker.locator('[data-column-apply]').click();
            await picker.locator('.column-toolbar > [data-preset-create]').click();
            const save=picker.locator('[data-preset-save-modal]'); await save.waitFor({state:'visible'});
            await save.locator('[data-preset-name]').fill('Без дати'); await save.locator('[type="submit"]').click(); await save.waitFor({state:'hidden'});
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="birth_date"]').check(); await picker.locator('[data-column-apply]').click();
            await open(); await menu.locator('[data-date-choices="years"] input[value="1993"]').check(); await apply();
            await picker.locator('[data-preset-apply]').click(); await page.waitForURL(url=>!url.searchParams.has('birth_date'));
            assert.equal(await header.isVisible(),false);
            await picker.locator('[data-table-back]').click(); await page.waitForURL(url=>url.searchParams.has('birth_date'));
            assert.equal(await header.isVisible(),true);
            assert.equal(new URL(page.url()).searchParams.get('unit_short'),'Перший');
            const presets=await page.evaluate(()=>JSON.parse(localStorage.getItem('project2:table-presets:person-positions')).presets);
            assert.equal('sort_by' in presets[0],false); assert.equal('birth_date_priority' in presets[0],false);
        });
        await scenario('date dropdown survives drag and resize without triggering sorting',async()=>{
            const url=page.url();
            await page.setViewportSize({width:2600,height:1000});
            await header.dragTo(table.locator('th[data-column-key="position_number"]'),{sourcePosition:{x:12,y:10},targetPosition:{x:12,y:10}});
            const keys=await table.locator('thead th').evaluateAll(nodes=>nodes.map(n=>n.dataset.columnKey));
            assert.equal(keys.indexOf('birth_date')+1,keys.indexOf('position_number'));
            const handle=header.locator('[data-column-resize]'); await handle.scrollIntoViewIfNeeded(); const box=await handle.boundingBox();
            await page.mouse.move(box.x+4,box.y+box.height/2); await page.mouse.down();
            await page.mouse.move(box.x-30,box.y+box.height/2,{steps:5}); await page.mouse.up();
            assert.equal(page.url(),url); await open(); assert.equal(await menu.isVisible(),true); await menu.locator('[data-date-cancel]').click();
        });
        await scenario('ordinary forms use shared input and never expose system timestamps',async()=>{
            await page.goto(base+'/persons/1/edit');
            assert.equal(await page.locator('[data-date-input]').count(),1);
            assert.equal(await page.locator('[name="created_at"], [name="updated_at"]').count(),0);
            await page.locator('[name="birth_day"]').fill('31'); await page.locator('[name="birth_month"]').fill('2');
            assert.equal(await page.locator('[name="birth_day"]').evaluate(n=>n.checkValidity()),false);
            await page.locator('[name="birth_day"]').fill('29'); await page.locator('[name="birth_year"]').fill('');
            assert.equal(await page.locator('[name="birth_day"]').evaluate(n=>n.checkValidity()),true);
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

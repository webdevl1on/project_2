const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const picker=page.locator('[data-column-picker]'),table=page.locator('#person-positions');
    const header=key=>table.locator(`th[data-column-key="${key}"]`);
    const visible=()=>table.locator('thead th:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.columnKey));
    const row=number=>table.locator('tbody tr').filter({has:page.locator('[data-column-key="position_number"] [data-column-value]',{hasText:String(number)})});
    async function scenario(name,fn){await fn();console.log(`PASS integration: ${name}`);}
    let before;
    try{
        await page.goto(base+'/person-positions');await page.evaluate(()=>localStorage.clear());await page.reload();
        await scenario('filter, manual layout, width and editor cooperate without implicit application',async()=>{
            await header('unit_short').locator('[data-bs-toggle=dropdown]').click();
            const menu=page.locator('[data-filter-key="unit_short"]');await menu.locator('input[value="Перший"]').check();
            await Promise.all([page.waitForURL(url=>url.searchParams.has('unit_short')),menu.locator('.apply-filter').click()]);
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="name_short"]').uncheck();
            await picker.locator('[data-column-apply]').click();
            await header('surname').dragTo(header('position_number'),{sourcePosition:{x:12,y:10},targetPosition:{x:12,y:10}});
            await header('surname').locator('[data-column-resize]').focus();
            await header('surname').locator('[data-column-resize]').press('ArrowLeft');
            before=await visible();
            await picker.locator('.column-toolbar > [data-preset-create]').click();
            const modal=picker.locator('[data-preset-save-modal]');await modal.locator('[data-preset-name]').fill('Робочий');
            await modal.locator('[type=submit]').click();await modal.waitFor({state:'hidden'});
            await picker.locator('[data-preset-edit]').click();
            const editor=picker.locator('[data-preset-editor-modal]');
            await editor.locator('[data-preset-selected-key="unit_short"] input').click();
            await editor.locator('[data-preset-selected-key="unit_short"]').waitFor({state:'detached'});
            await editor.locator('[data-preset-editor-name]').fill('Без взводу');
            await editor.locator('[data-preset-editor-save]').click();await editor.waitFor({state:'hidden'});
            assert.deepEqual(await visible(),before);assert.equal(await table.locator('tbody tr').count(),2);
            await picker.locator('[data-preset-apply]').click();await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.equal(await table.locator('tbody tr').count(),3);
            assert.equal((await visible()).includes('unit_short'),false);
            assert.equal((await visible()).includes('name_short'),false);
            assert.ok(Math.abs((await header('surname').boundingBox()).width-170)<2);
        });
        await scenario('ordinary sort and actual assignment handlers survive preset DOM reorder',async()=>{
            await header('position_number').locator('.position-column-heading > a').click();
            await page.waitForURL(url=>url.searchParams.get('direction')==='desc');
            const url=page.url();
            const historyBefore=await page.evaluate(()=>localStorage.getItem('project2:table-history:person-positions'));
            // Release the existing historical assignment, then restore it with a real POST.
            await row(20).locator('[data-person-label]').click();
            await row(20).locator('[data-person-option=""]').click();
            await row(20).locator('form [type=submit]').click();
            await page.locator('#staff-assignment-confirm').waitFor({state:'visible'});
            await Promise.all([page.waitForNavigation(),page.locator('[data-assignment-confirm-yes]').click()]);
            await row(20).locator('[data-person-label]').click();
            await row(20).locator('[data-person-option="2"]').click();
            await Promise.all([page.waitForNavigation(),row(20).locator('form [type=submit]').click()]);
            assert.equal(await row(20).locator('[data-person-value]').inputValue(),'2');
            assert.equal(new URL(page.url()).searchParams.get('direction'),'desc');
            assert.equal(await page.evaluate(()=>localStorage.getItem('project2:table-history:person-positions')),historyBefore);
            assert.deepEqual((await table.locator('tbody [data-column-key="position_number"]').allTextContents()).map(n=>n.trim()),['30','20','10']);
        });
        await scenario('undo restores only layout and filters, keeps current sort, widths and assignments',async()=>{
            await picker.locator('[data-table-back]').click();await page.waitForURL(url=>url.searchParams.has('unit_short'));
            assert.deepEqual(await visible(),before);assert.equal(new URL(page.url()).searchParams.get('direction'),'desc');
            assert.equal(await table.locator('tbody tr').count(),2);
            assert.equal(await row(20).locator('[data-person-value]').inputValue(),'2');
            assert.equal(await row(10).locator('[data-person-value]').inputValue(),'1');
            assert.ok(Math.abs((await header('surname').boundingBox()).width-170)<2);
            await picker.locator('[data-table-forward]').click();await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.equal(await table.locator('tbody tr').count(),3);
            await page.reload();assert.equal((await visible()).includes('unit_short'),false);
            assert.equal(await row(20).locator('[data-person-value]').inputValue(),'2');
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const picker=page.locator('[data-column-picker]').first(),table=page.locator('#person-positions');
    const history=()=>page.evaluate(()=>JSON.parse(localStorage.getItem('project2:table-history:person-positions')));
    const visible=()=>table.locator('thead th:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.columnKey));
    const order=()=>table.locator('thead th').evaluateAll(nodes=>nodes.map(n=>n.dataset.columnKey));
    const numbers=async()=>(await table.locator('tbody [data-column-key="position_number"]').allTextContents()).map(n=>n.trim());
    async function scenario(name,fn){await fn();console.log(`PASS history: ${name}`);}
    async function change(key,checked){
        await picker.locator('[data-column-toggle]').click();
        await picker.locator(`[data-visibility-tree] [data-column-choice="${key}"]`).setChecked(checked);
        await picker.locator('[data-column-apply]').click();
    }
    async function filterUnit(){
        await table.locator('th[data-column-key="unit_short"] [data-bs-toggle=dropdown]').click();
        const menu=page.locator('[data-filter-key="unit_short"]');await menu.locator('input[value="Перший"]').check();
        await Promise.all([page.waitForURL(url=>url.searchParams.has('unit_short')),menu.locator('.apply-filter').click()]);
    }
    async function applyPreset(){await picker.locator('[data-preset-apply="without-unit"]').click();await page.waitForURL(url=>!url.searchParams.has('unit_short'));}
    try{
        await page.goto(base+'/person-positions');await page.evaluate(()=>localStorage.clear());
        await page.evaluate(()=>{
            const config=JSON.parse(document.querySelector('[data-column-config]').textContent);
            const preset={version:1,id:'without-unit',table_id:config.id,name:'Без взводу',columns:config.groups.flatMap(g=>g.columns).map(c=>c.key).filter(k=>k!=='unit_short')};
            localStorage.setItem(`project2:table-presets:${config.id}`,JSON.stringify({version:1,presets:[preset]}));
        });
        await page.reload();
        await scenario('preset undo/redo restores visibility, drag order, URL filter and SQL results',async()=>{
            assert.equal(await picker.locator('[data-table-back]').isDisabled(),true);
            await filterUnit();assert.deepEqual(await numbers(),['10','20']);
            await change('name_short',false);
            await table.locator('th[data-column-key="surname"]').dragTo(table.locator('th[data-column-key="position_number"]'),{sourcePosition:{x:12,y:10},targetPosition:{x:12,y:10}});
            const beforeVisible=await visible(),beforeOrder=await order();
            assert.equal(beforeOrder[1],'surname');
            assert.equal((await history()).entries.length,4);
            await applyPreset();
            assert.equal((await history()).entries.length,5);
            assert.deepEqual(await numbers(),['10','20','30']);
            assert.equal((await visible()).includes('unit_short'),false);
            await picker.locator('[data-table-back]').click();
            await page.waitForURL(url=>url.searchParams.has('unit_short'));
            assert.deepEqual(await visible(),beforeVisible);assert.deepEqual(await order(),beforeOrder);
            assert.deepEqual(await numbers(),['10','20']);
            assert.equal(new URL(page.url()).searchParams.get('filter_order'),'unit_short');
            assert.equal((await history()).cursor,3);
            await page.reload();assert.equal((await history()).cursor,3);
            assert.equal(await picker.locator('[data-table-forward]').isEnabled(),true);
            await picker.locator('[data-table-forward]').click();
            await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.equal((await visible()).includes('unit_short'),false);assert.deepEqual(await numbers(),['10','20','30']);
        });
        await scenario('sorting and resizing are not independent history steps',async()=>{
            const before=await history();
            await table.locator('th[data-column-key="position_number"] .position-column-heading > a').click();
            await page.waitForURL(url=>url.searchParams.get('direction')==='desc');
            assert.deepEqual(await history(),before);
            const handle=table.locator('[data-column-resize="position_number"]');await handle.focus();await handle.press('ArrowRight');
            assert.deepEqual(await history(),before);
        });
        await scenario('native browser Back/Forward restores matching layouts and filters',async()=>{
            await change('unit_short',true);await filterUnit();
            const before=await visible();
            await applyPreset();
            await page.goBack();
            await page.waitForURL(url=>url.searchParams.has('unit_short'));
            assert.deepEqual(await visible(),before);assert.equal((await numbers()).length,2);
            await page.goForward();
            await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            assert.equal((await visible()).includes('unit_short'),false);assert.equal((await numbers()).length,3);
        });
        await scenario('limit of five, disabled ends, branching and duplicate suppression',async()=>{
            for(let i=0;i<7;i++) await change('assignment',i%2===1);
            assert.equal((await history()).entries.length,5);
            for(let i=0;i<4;i++) await picker.locator('[data-table-back]').click();
            assert.equal(await picker.locator('[data-table-back]').isDisabled(),true);
            assert.equal(await picker.locator('[data-table-forward]').isEnabled(),true);
            await change('rank',false);
            assert.equal((await history()).entries.length,2);assert.equal((await history()).cursor,1);
            assert.equal(await picker.locator('[data-table-forward]').isDisabled(),true);
            await change('rank',false);assert.equal((await history()).entries.length,2);
        });
        await scenario('invalid persisted history resets safely',async()=>{
            await page.evaluate(()=>localStorage.setItem('project2:table-history:person-positions',JSON.stringify({version:1,entries:[null],cursor:0})));
            await page.reload();assert.equal((await history()).entries.length,1);
            assert.equal(await picker.locator('[data-table-back]').isDisabled(),true);
        });
        await scenario('independent histories for two tables and no JS errors',async()=>{
            await page.goto(base+'/_column-test/two-tables');
            await page.evaluate(()=>{
                for(const id of ['example-first','example-second']){
                    localStorage.removeItem(`project2:table-history:${id}`);localStorage.removeItem(`project2:table-columns:${id}`);
                }
            });await page.reload();
            const second=page.locator('[data-column-picker]').nth(1);
            await change('code',true);
            assert.equal(await picker.locator('[data-table-back]').isEnabled(),true);
            assert.equal(await second.locator('[data-table-back]').isDisabled(),true);
            await picker.locator('[data-table-back]').click();
            assert.equal(await page.locator('#example-first th[data-column-key="code"]').isVisible(),false);
            assert.equal(await page.locator('#example-second th[data-column-key="code"]').isVisible(),false);
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

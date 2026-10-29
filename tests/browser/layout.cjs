const {openAssignment,openStaffActions}=require('./table_helpers.cjs');
const assert = require('node:assert/strict');
module.exports = async ({context,base}) => {
    const page=await context.newPage(), errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const table=page.locator('#person-positions');
    const picker=page.locator('[data-column-picker]');
    const header=key=>table.locator(`th[data-column-key="${key}"]`);
    const order=()=>table.locator('thead th').evaluateAll(nodes=>nodes.map(n=>n.dataset.columnKey));
    async function scenario(name,fn){await fn();console.log(`PASS layout: ${name}`);}
    async function drag(source,target){
        // Bootstrap hides the modal before its fading backdrop is detached.
        await page.locator('.modal-backdrop').waitFor({state:'detached'});
        await header(source).dragTo(header(target),{sourcePosition:{x:12,y:10},targetPosition:{x:12,y:10}});
    }
    try {
        await page.goto(base+'/person-positions'); await page.evaluate(()=>localStorage.clear()); await page.reload();
        await scenario('system numbering is fixed, visible and has no resize handle', async()=>{
            assert.equal(await header('row_number').getAttribute('draggable'),'false');
            assert.equal(await header('row_number').locator('[data-column-resize]').count(),0);
            await picker.locator('[data-column-toggle]').click();
            assert.equal(await picker.locator('[data-visibility-tree] [data-column-choice="row_number"]').isDisabled(),true);
            await page.keyboard.press('Escape');
        });
        await scenario('real drag preserves keyed cells and does not trigger sorting', async()=>{
            const url=page.url();
            await drag('name_short','position_number');
            assert.deepEqual((await order()).slice(0,3),['row_number','name_short','position_number']);
            const rows=await table.locator('tbody tr').evaluateAll(rows=>rows.map(row=>Array.from(row.querySelectorAll('td[data-column-key]')).map(cell=>cell.dataset.columnKey)));
            for(const keys of rows) assert.deepEqual(keys,await order());
            assert.equal(page.url(),url);
            assert.equal(await table.locator('tbody tr').first().locator('[data-column-key="position_number"]').innerText(),'10');
            await page.reload();
            assert.equal((await order())[1],'name_short');
        });
        await scenario('column resize clamps minimum, ellipsis keeps full text and copy value', async()=>{
            const key='name_nominative';
            const handle=header(key).locator('[data-column-resize]');
            await handle.scrollIntoViewIfNeeded();
            let box=await handle.boundingBox();
            const url=page.url(), before=await order();
            await page.mouse.move(box.x+4,box.y+box.height/2);
            await page.mouse.down();
            await page.mouse.move(box.x-250,box.y+box.height/2,{steps:10});
            await page.mouse.up();
            assert.ok(Math.abs((await header(key).boundingBox()).width-100)<2);
            assert.equal(page.url(),url);
            assert.deepEqual(await order(),before);
            const value=table.locator('tbody tr').first().locator(`[data-column-key="${key}"] [data-column-value]`);
            assert.equal(await value.getAttribute('title'),await value.textContent());
            const text=await value.textContent();
            assert.equal(await value.evaluate(node=>{
                const range=document.createRange();range.selectNodeContents(node);
                const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);return selection.toString();
            }),text);
            assert.equal(await value.evaluate(node=>getComputedStyle(node).textOverflow),'ellipsis');
            assert.equal(await value.evaluate(node=>node.scrollWidth>node.clientWidth),true);
            await page.reload();
            assert.ok(Math.abs((await header(key).boundingBox()).width-100)<2);
        });
        await scenario('presets save drag order but leave current widths untouched', async()=>{
            // Keep both drag endpoints visible; dragTo does not emulate scrollbar dragging.
            await page.setViewportSize({width:2600,height:1000});
            const visibleOrder=()=>table.locator('thead th:visible').evaluateAll(nodes=>nodes.map(node=>node.dataset.columnKey));
            const savedOrder=await visibleOrder();
            await picker.locator('.column-toolbar > [data-preset-create]').click();
            const modal=picker.locator('[data-preset-save-modal]');
            await modal.locator('[data-preset-name]').fill('Порядок');
            await modal.locator('[type=submit]').click();await modal.waitFor({state:'hidden'});
            await drag('surname','name_short');
            assert.notDeepEqual(await visibleOrder(),savedOrder);
            await picker.locator('[data-preset-apply]').click();
            assert.deepEqual(await visibleOrder(),savedOrder);
            assert.ok(Math.abs((await header('name_nominative').boundingBox()).width-100)<2);
            const presets=await page.evaluate(()=>JSON.parse(localStorage.getItem('project2:table-presets:person-positions')).presets);
            assert.equal(Object.hasOwn(presets[0],'widths'),false);
        });
        await scenario('filter and assignment handlers survive moving DOM nodes', async()=>{
            await header('unit_short').locator('[data-bs-toggle=dropdown]').click();
            assert.equal(await page.locator('[data-filter-key="unit_short"]').isVisible(),true);
            await page.keyboard.press('Escape');
            await openAssignment(table.locator('tbody tr').first());await table.locator('[data-person-label]').first().click();
            const search=table.locator('.person-search').first();
            await search.fill('Бета');
            assert.equal(await table.locator('[data-person-picker]').first().locator('[data-person-option="1"]').evaluate(n=>n.hidden),true);
            assert.deepEqual(errors,[]);
        });
    } finally {await page.close();}
};

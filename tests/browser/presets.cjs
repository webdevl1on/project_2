const assert = require('node:assert/strict');
module.exports = async ({context,base}) => {
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const picker = page.locator('[data-column-picker]').first();
    const table = page.locator('#person-positions');
    const save = picker.locator('[data-preset-save-modal]');
    const editor = picker.locator('[data-preset-editor-modal]');
    const del = picker.locator('[data-preset-delete-modal]');
    const presetKey = 'project2:table-presets:person-positions';
    const stored = () => page.evaluate(key => JSON.parse(localStorage.getItem(key))?.presets || [],presetKey);
    const snapshot = () => table.locator('thead th:visible').evaluateAll(nodes => nodes.map(node=>node.dataset.columnKey));
    async function openSave() { await picker.locator('.column-toolbar > [data-preset-create]').click(); await save.waitFor({state:'visible'}); }
    async function submit(name) { await save.locator('[data-preset-name]').fill(name); await save.locator('[type=submit]').click(); }
    async function close(modal) { await modal.locator('[data-bs-dismiss=modal]:visible').last().click(); await modal.waitFor({state:'hidden'}); }
    async function scenario(name,action) { await action(); console.log(`PASS presets: ${name}`); }
    try {
        await page.goto(base+'/person-positions');
        await page.evaluate(()=>localStorage.clear());
        await page.reload();
        await scenario('name validation and shared save modal from both buttons',async()=>{
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('.dropdown-menu [data-preset-create]').click();
            await submit('   ');
            assert.equal(await save.locator('[data-preset-save-error]').isVisible(),true);
            assert.equal(await save.locator('[data-preset-name]').getAttribute('maxlength'),'30');
            await save.locator('[data-preset-name]').evaluate(node=>node.value='x'.repeat(31));
            await save.locator('[type=submit]').click();
            assert.match(await save.locator('[data-preset-save-error]').innerText(),/30/);
            await submit('Початковий');
            await save.waitFor({state:'hidden'});
            const [preset] = await stored();
            assert.equal(preset.columns.length,10);
            assert.equal(preset.version,1);
            assert.equal(preset.table_id,'person-positions');
            assert.ok(preset.id);
            assert.equal(await picker.locator('[data-preset-apply]').count(),1);
        });
        await scenario('manual changes do not mutate preset; click applies without confirmation',async()=>{
            const original = (await stored())[0];
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="unit_short"]').uncheck();
            await picker.locator('[data-column-apply]').click();
            assert.deepEqual((await stored())[0],original);
            assert.equal((await snapshot()).includes('unit_short'),false);
            await picker.locator('[data-preset-apply]').click();
            assert.equal((await snapshot()).includes('unit_short'),true);
            assert.equal(await picker.locator('.modal.show').count(),0);
        });
        await scenario('duplicate name requires explicit overwrite or name editing/cancel',async()=>{
            const id = (await stored())[0].id;
            await openSave();
            await submit('Початковий');
            await save.locator('[data-preset-conflict]').waitFor({state:'visible'});
            await save.locator('[data-preset-back]').click();
            await submit('Інший');
            await save.waitFor({state:'hidden'});
            assert.equal((await stored()).length,2);
            await picker.locator('[data-column-toggle]').click();
            await picker.locator('[data-visibility-tree] [data-column-choice="unit_short"]').uncheck();
            await picker.locator('[data-column-apply]').click();
            await openSave(); await submit('Початковий');
            assert.equal((await stored())[0].columns.includes('unit_short'),true);
            await save.locator('[data-preset-overwrite]').click();
            await save.waitFor({state:'hidden'});
            assert.equal((await stored())[0].id,id);
            assert.equal((await stored())[0].columns.includes('unit_short'),false);
            await openSave(); await submit('Початковий'); await close(save);
            assert.equal((await stored()).length,2);
        });
        await scenario('gear does not apply; grouped editor, independent arrows and rename',async()=>{
            const before = await snapshot();
            await picker.locator('[data-preset-edit]').first().click();
            await editor.waitFor({state:'visible'});
            assert.deepEqual(await snapshot(),before);
            assert.equal(await editor.locator('[data-preset-editor-save]').isDisabled(),true);
            assert.equal(await editor.locator('[data-preset-up="row_number"]').isDisabled(),true);
            const group = editor.locator('[data-column-group]:has([aria-controls$="-group-position"])');
            assert.equal(await group.locator('[data-column-group-choice]').evaluate(node=>node.indeterminate),true);
            await editor.locator('[data-column-choice="unit_short"]').check();
            assert.equal(await group.locator('[data-column-group-choice]').isChecked(),true);
            assert.equal(await editor.locator('[data-preset-selected-key]').last().getAttribute('data-preset-selected-key'),'unit_short');
            await editor.locator('[data-preset-up="unit_short"]').click();
            assert.equal(await editor.locator('[data-preset-selected-key]').nth(8).getAttribute('data-preset-selected-key'),'unit_short');
            await group.locator('[data-column-group-choice]').uncheck();
            assert.equal(await editor.locator('[data-preset-selected-key="unit_short"]').count(),0);
            await group.locator('[data-column-group-choice]').check();
            await editor.locator('[data-preset-editor-name]').fill('Оновлений');
            await editor.locator('[data-preset-editor-save]').click();
            await editor.waitFor({state:'hidden'});
            assert.deepEqual(await snapshot(),before);
            const updated = (await stored())[0];
            assert.equal(updated.name,'Оновлений');
            assert.equal(updated.columns.at(-1),'name_nominative');
            await picker.locator('[data-preset-apply]').first().click();
            assert.deepEqual(await snapshot(),updated.columns);
        });
        await scenario('cancel editor and confirmed deletion leave current view untouched',async()=>{
            const before = await snapshot();
            await picker.locator('[data-preset-edit]').first().click();
            await editor.locator('[data-preset-editor-name]').fill('Незбережено');
            await close(editor);
            assert.equal((await stored())[0].name,'Оновлений');
            await picker.locator('[data-preset-edit]').first().click();
            await editor.locator('[data-preset-delete]').click();
            await del.waitFor({state:'visible'});
            assert.equal((await stored()).length,2);
            await del.locator('[data-preset-delete-cancel]').click();
            await editor.waitFor({state:'visible'});
            await editor.locator('[data-preset-delete]').click();
            await del.locator('[data-preset-delete-confirm]').click();
            await del.waitFor({state:'hidden'});
            assert.equal((await stored()).length,1);
            assert.deepEqual(await snapshot(),before);
        });
        await scenario('30-character names, HTTP UUID fallback and wrapping preset buttons',async()=>{
            await page.evaluate(()=>Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true}));
            const name='Ж'.repeat(30);
            await openSave();await submit(name);await save.waitFor({state:'hidden'});
            assert.equal((await stored()).some(p=>p.name===name),true);
            const preset=(await stored()).find(p=>p.name===name);
            assert.match(preset.id,/^[0-9a-f-]{36}$/);
            await page.evaluate(({key,preset})=>{
                const presets=Array.from({length:12},(_,n)=>({...preset,id:`many-${n}`,name:n===0?preset.name:`Пресет ${n}`}));
                localStorage.setItem(key,JSON.stringify({version:1,presets}));
            },{key:presetKey,preset});
            await page.reload();await page.setViewportSize({width:390,height:844});
            assert.equal(await picker.locator('[data-preset-apply]').count(),12);
            const first=await picker.locator('[data-preset-apply]').first().boundingBox();
            const last=await picker.locator('[data-preset-apply]').last().boundingBox();
            assert.ok(first.height>45);assert.ok(last.y>first.y);
            await page.setViewportSize({width:1280,height:720});
        });
        await scenario('obsolete presets warn without mutation; unusable presets blocked',async()=>{
            const presets = [
                {version:1,id:'stale',table_id:'person-positions',name:'Старий',columns:['gone','surname']},
                {version:1,id:'empty',table_id:'person-positions',name:'Без колонок',columns:['gone']},
            ];
            await page.evaluate(({key,presets})=>localStorage.setItem(key,JSON.stringify({version:1,presets})),{key:presetKey,presets});
            await page.reload();
            assert.match(await picker.locator('[data-preset-stale]').first().innerText(),/gone/);
            await picker.locator('[data-preset-apply="stale"]').click();
            assert.deepEqual(await snapshot(),['row_number','surname']);
            assert.deepEqual(await stored(),presets);
            await picker.locator('[data-preset-apply="empty"]').click();
            assert.deepEqual(await snapshot(),['row_number','surname']);
            assert.match(await picker.locator('[data-preset-notice]').innerText(),/інформаційних/);
        });
        await scenario('presets isolated per table and no JavaScript errors',async()=>{
            await page.goto(base+'/_column-test/two-tables');
            const second = page.locator('[data-column-picker]').nth(1);
            await openSave(); await submit('Спільна назва'); await save.waitFor({state:'hidden'});
            await second.locator('.column-toolbar > [data-preset-create]').click();
            await second.locator('[data-preset-name]').fill('Спільна назва');
            await second.locator('[data-preset-save-modal] [type=submit]').click();
            await second.locator('[data-preset-save-modal]').waitFor({state:'hidden'});
            assert.equal(await picker.locator('[data-preset-apply]').count(),1);
            assert.equal(await second.locator('[data-preset-apply]').count(),1);
            await page.reload();
            assert.equal(await second.locator('[data-preset-apply]').count(),1);
            assert.deepEqual(errors,[]);
        });
    } finally { await page.close(); }
};

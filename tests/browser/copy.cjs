const {openAssignment,openStaffActions}=require('./table_helpers.cjs');
const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const table=page.locator('#person-positions'),picker=page.locator('[data-column-picker]');
    const cell=(r,key)=>table.locator(`tbody tr:nth-child(${r}) td[data-column-key="${key}"]`);
    const selected=()=>table.locator('.table-cell-selected').count();
    async function scenario(name,fn){await fn();console.log(`PASS copy: ${name}`);}
    const matrix=()=>page.evaluate(()=>TableColumns.controllers.get('person-positions').selection.matrix());
    async function mockClipboard(){await page.evaluate(()=>{
        window.copied=[];
        Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
            writeText:async text=>window.copied.push({text}),
            write:async items=>{const item=items[0];window.copied.push({html:await (await item.getType('text/html')).text(),text:await(await item.getType('text/plain')).text()});}
        }});
    });}
    try{
        await page.setViewportSize({width:1280,height:1500});
        await page.goto(base+'/person-positions');await page.evaluate(()=>localStorage.clear());await page.reload();
        await mockClipboard();
        await scenario('drag directly over surname text selects a vertical column, never browser text',async()=>{
            await cell(1,'surname').scrollIntoViewIfNeeded();
            const coords=await table.locator('tbody td[data-column-key="surname"] [data-column-value]').evaluateAll(nodes=>nodes.map(node=>{
                const range=document.createRange();range.selectNodeContents(node);const r=range.getBoundingClientRect();
                return {x:r.x+Math.min(12,r.width/2),y:r.y+r.height/2};
            }));
            await page.mouse.move(coords[0].x,coords[0].y);await page.mouse.down();
            await page.mouse.move(coords[2].x,coords[2].y,{steps:20});await page.mouse.up();
            assert.equal(await selected(),3);
            assert.deepEqual(await matrix(),[['Альфа'],['Бета'],['-']]);
            assert.equal(await page.evaluate(()=>window.getSelection().toString()),'');
            await page.keyboard.press('Escape');
        });
        await scenario('header menu selects the entire column and the button copies only that column',async()=>{
            await table.locator('th[data-column-key="surname"]').scrollIntoViewIfNeeded();
            await table.locator('th[data-column-key="surname"] [data-bs-toggle]').click();
            await table.locator('th[data-column-key="surname"] [data-column-select]').click();
            assert.equal(await selected(),3);assert.deepEqual(await matrix(),[['Альфа'],['Бета'],['-']]);
            await picker.locator('[data-table-copy]').click();await page.waitForFunction(()=>copied.length>0);
            assert.equal(await page.evaluate(()=>copied.at(-1).text),'Альфа\nБета\n-');
            await page.keyboard.press('Escape');await page.evaluate(()=>copied=[]);
        });
        await scenario('single cell and button use Excel TSV',async()=>{
            await cell(1,'unit_short').click();assert.equal(await selected(),1);
            await picker.locator('[data-table-copy]').click();
            assert.equal(await page.evaluate(()=>copied.at(-1).text),'Перший');
            assert.equal(await page.evaluate(()=>copied.length),1);
            assert.deepEqual(await matrix(),[['Перший']]);
        });
        await scenario('drag and Shift extend rectangles, Ctrl adds sparse cells, Escape clears',async()=>{
            await cell(1,'position_number').scrollIntoViewIfNeeded();
            let a=await cell(1,'position_number').boundingBox(),b=await cell(2,'name_short').boundingBox();
            await page.mouse.move(a.x+10,a.y+10);await page.mouse.down();await page.mouse.move(b.x+10,b.y+10,{steps:10});await page.mouse.up();
            assert.equal(await selected(),6);
            await cell(3,'name_short').click({modifiers:['Shift']});assert.equal(await selected(),9);
            await page.keyboard.press('Escape');assert.equal(await selected(),0);
            await cell(1,'position_number').click();await cell(2,'name_short').click({modifiers:['Control']});
            assert.deepEqual(await matrix(),[['10','',''],['','','Стрілець']]);
            a=await cell(1,'position_number').boundingBox();b=await cell(2,'unit_short').boundingBox();
            await page.keyboard.down('Control');await page.mouse.move(a.x+10,a.y+10);await page.mouse.down();
            await page.mouse.move(b.x+10,b.y+10,{steps:6});await page.mouse.up();await page.keyboard.up('Control');
            assert.equal(await selected(),5);
            assert.deepEqual(await matrix(),[['10','Перший',''],['20','Перший','Стрілець']]);
            await page.keyboard.press('Escape');assert.equal(await picker.locator('[data-table-copy]').isDisabled(),true);
        });
        await scenario('Ctrl+A and Ctrl+C remain native and do not change cell selection or invoke the exporter',async()=>{
            await cell(1,'unit_short').click();
            const before=await page.evaluate(()=>copied.length);
            await page.evaluate(()=>{
                window.shortcuts=[];
                document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&['a','c'].includes(event.key.toLowerCase())) shortcuts.push(event.defaultPrevented);});
            });
            await table.focus();await page.keyboard.press('Control+a');await page.keyboard.press('Control+c');
            assert.equal(await selected(),1);assert.equal(await page.evaluate(()=>copied.length),before);
            assert.deepEqual(await page.evaluate(()=>shortcuts),[false,false]);
            assert.ok(await page.evaluate(()=>window.getSelection().toString().length>0));
            await page.keyboard.press('Escape');
            await openAssignment(table.locator('tbody tr').first());await table.locator('[data-person-label]').first().click();
            const input=table.locator('.person-search').first();await input.fill('Тест');await input.press('Control+a');
            assert.equal(await selected(),0);assert.equal(await input.evaluate(n=>n.selectionEnd-n.selectionStart),4);
            await input.fill('');await page.keyboard.press('Escape');
        });
        await scenario('Word writes HTML and plain MIME, format persists, dates and empty values are copied',async()=>{
            await picker.locator('[data-copy-format][value="word"]').check();
            await cell(1,'birth_date').click();await picker.locator('[data-table-copy]').click();
            await page.waitForFunction(()=>copied.at(-1)?.html);
            assert.match(await page.evaluate(()=>copied.at(-1).html),/<table/);
            assert.equal(await page.evaluate(()=>copied.at(-1).text),'15.03.1993');
            await page.reload();assert.equal(await picker.locator('[data-copy-format][value="word"]').isChecked(),true);
            await mockClipboard();await cell(2,'birth_date').click();await cell(3,'birth_date').click({modifiers:['Shift']});
            await picker.locator('[data-table-copy]').click();await page.waitForFunction(()=>copied.length>0);
            assert.equal(await page.evaluate(()=>copied.at(-1).text),'15._.1993\n-');
        });
        await scenario('HTML unavailable falls back to plain with an explicit warning; total denial reports failure',async()=>{
            await page.evaluate(()=>{navigator.clipboard.write=async()=>{throw Error('Denied')};document.execCommand=()=>false;});
            await picker.locator('[data-table-copy]').click();
            await page.waitForFunction(()=>document.querySelector('[data-copy-status]').textContent.includes('лише текст'));
            await page.evaluate(()=>{navigator.clipboard.writeText=async()=>{throw Error('Denied')};});
            await picker.locator('[data-table-copy]').click();
            await page.waitForFunction(()=>document.querySelector('[data-copy-status]').textContent.includes('Не вдалося'));
        });
        await scenario('header hiding clears filter, syncs tree, supports undo/redo and date menus',async()=>{
            await page.goto(base+'/person-positions');await page.evaluate(()=>localStorage.clear());await page.reload();
            await table.locator('th[data-column-key="unit_short"] [data-bs-toggle]').click();
            await page.locator('[data-filter-key="unit_short"] input[value="Перший"]').check();
            await Promise.all([page.waitForNavigation(),page.locator('[data-filter-key="unit_short"] .apply-filter').click()]);
            await table.locator('th[data-column-key="unit_short"] [data-bs-toggle]').click();
            await Promise.all([page.waitForURL(url=>!url.searchParams.has('unit_short')),page.locator('[data-filter-key="unit_short"] [data-column-hide]').click()]);
            assert.equal(await table.locator('th[data-column-key="unit_short"]').isVisible(),false);
            assert.equal(await picker.locator('[data-visibility-tree] [data-column-choice="unit_short"]').isChecked(),false);
            await picker.locator('[data-table-back]').click();await page.waitForURL(url=>url.searchParams.has('unit_short'));
            assert.equal(await table.locator('th[data-column-key="unit_short"]').isVisible(),true);
            await picker.locator('[data-table-forward]').click();await page.waitForURL(url=>!url.searchParams.has('unit_short'));
            await table.locator('th[data-column-key="birth_date"]').scrollIntoViewIfNeeded();
            await table.locator('th[data-column-key="birth_date"] [data-bs-toggle]').click();
            await page.locator('[data-date-column-key="birth_date"] [data-column-hide]').click();
            assert.equal(await table.locator('th[data-column-key="birth_date"]').isVisible(),false);
            assert.equal(await table.locator('th[data-column-key="row_number"] [data-column-hide]').count(),0);
        });
        await scenario('current DOM order and visibility drive copying, last informational column is protected',async()=>{
            await page.evaluate(()=>{
                const c=TableColumns.controllers.get('person-positions');
                c.commitLayout({visible:['row_number','birth_date','position_number'],order:['row_number','birth_date','position_number']});
            });
            await cell(1,'row_number').click();await cell(1,'position_number').click({modifiers:['Shift']});
            assert.deepEqual((await matrix())[0],['1','15.03.1993','10']);
            await page.evaluate(()=>TableColumns.controllers.get('person-positions').commitLayout({visible:['row_number','position_number'],order:['row_number','position_number']}));
            await table.locator('th[data-column-key="position_number"] [data-bs-toggle]').click();
            await page.locator('[data-filter-key="position_number"] [data-column-hide]').click();
            assert.equal(await table.locator('th[data-column-key="position_number"]').isVisible(),true);
            assert.deepEqual(errors,[]);
        });
        await scenario('real Chromium clipboard contains both Word MIME types; legacy HTML fallback works',async()=>{
            await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});
            await page.goto(base+'/person-positions');
            await picker.locator('[data-copy-format][value="word"]').check();
            await cell(1,'position_number').click();
            await picker.locator('[data-table-copy]').click();
            await page.waitForFunction(()=>document.querySelector('[data-copy-status]').textContent.includes('для Word'));
            let contents=await page.evaluate(async()=>{const [item]=await navigator.clipboard.read();return {types:item.types,text:await(await item.getType('text/plain')).text(),html:await(await item.getType('text/html')).text()};});
            assert.ok(contents.types.includes('text/html'));assert.equal(contents.text,'10');assert.match(contents.html,/<table/);
            await page.evaluate(()=>Object.defineProperty(navigator.clipboard,'write',{configurable:true,value:async()=>{throw Error('Use legacy');}}));
            await cell(2,'position_number').click();
            await picker.locator('[data-table-copy]').click();
            await page.waitForFunction(()=>document.querySelector('[data-copy-status]').textContent.includes('для Word'));
            contents=await page.evaluate(async()=>{const [item]=await navigator.clipboard.read();return {types:item.types,text:await(await item.getType('text/plain')).text()};});
            assert.equal(contents.text,'20');assert.ok(contents.types.includes('text/html'));
        });
        await scenario('second table has independent selection and format storage',async()=>{
            await page.goto(base+'/_column-test/two-tables');
            await page.locator('[data-column-picker]').first().locator('[data-copy-format][value="word"]').check();
            await page.locator('#example-first tbody td[data-column-key="title"]').click();
            assert.equal(await page.locator('#example-first .table-cell-selected').count(),1);
            await page.evaluate(()=>{
                const cell=document.querySelector('#example-first tbody td');
                cell.insertAdjacentHTML('beforeend','<button>Не копіювати</button><span role="img">Іконка</span>');
            });
            assert.deepEqual(await page.evaluate(()=>TableColumns.controllers.get('example-first').selection.matrix()),[['Значення']]);
            await page.locator('#example-first button').click();
            assert.equal(await page.locator('#example-first .table-cell-selected').count(),1);
            assert.equal(await page.locator('#example-second .table-cell-selected').count(),0);
            assert.equal(await page.locator('[data-column-picker]').nth(1).locator('[data-copy-format][value="excel"]').isChecked(),true);
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

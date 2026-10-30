const assert=require('node:assert/strict');
const {openAssignment}=require('./table_helpers.cjs');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.setViewportSize({width:1700,height:1000});
 const table=()=>page.locator('table[data-column-table]');
 const picker=()=>page.locator('[data-column-picker]');
 const row=number=>page.locator('#person-positions tbody tr').filter({has:page.locator('[data-column-key="position_number"] [data-column-value]').filter({hasText:new RegExp('^\\s*'+number+'\\s*$')})});
 const controller=()=>page.evaluate(()=>TableColumns.controllers.get(document.querySelector('[data-column-table]').id).selection.matrix());
 const visit=async path=>{await page.goto(base+path);await picker().locator('[data-columns-ready]').count();};
 const formatting=async()=>{const panel=picker().locator('[data-table-format]');if(!await panel.evaluate(n=>n.open))await panel.locator('summary').click();};
 const scenario=async(name,fn)=>{await fn();console.log('PASS workspace: '+name);};
 try{
  await visit('/person-positions');await page.evaluate(()=>localStorage.clear());await page.reload();
  await scenario('shared active navigation, compact default rows and genuine profile links',async()=>{
   assert.equal(await page.locator('.app-navigation [aria-current="page"]').innerText(),'Штатка');
   assert.equal(await row(10).locator('[data-assignment-editor]').isHidden(),true);
   assert.equal(await row(10).locator('[data-column-key="row_number"] a').getAttribute('href'),'/person_full_info/1');
   assert.equal(await row(30).locator('[data-column-key="row_number"] a').count(),0);
   const heights=await table().locator('tbody tr').evaluateAll(rows=>rows.map(r=>r.getBoundingClientRect().height));assert.ok(heights.every(h=>Math.abs(h-40)<2),JSON.stringify(heights));
  });
  await scenario('profile icon alone navigates, leaves selection untouched, and is excluded from Excel/Word copy',async()=>{
   await page.evaluate(()=>{const c=TableColumns.controllers.get('person-positions');c.commitLayout({visible:[...c.state.layout.visible,'full_name'],order:c.state.layout.order});});
   const name=row(10).locator('[data-column-key="full_name"]');
   assert.equal(await name.locator('a').count(),0);
   await name.click();const nameMatrix=await controller();assert.match(nameMatrix[0][0],/Альфа/);
   const link=row(10).locator('.staff-profile-link');
   assert.equal(await link.getAttribute('title'),'Відкрити анкету');
   assert.equal(await link.getAttribute('aria-label'),'Відкрити анкету');
   await link.evaluate(n=>n.addEventListener('click',event=>event.preventDefault(),{once:true}));
   const beforeURL=page.url();await link.locator('svg').click();
   assert.equal(page.url(),beforeURL);assert.deepEqual(await controller(),nameMatrix);
   assert.equal(await table().locator('[data-assignment-editor]:visible').count(),0);
   await page.evaluate(()=>{window.profileCopies=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{
    writeText:async text=>profileCopies.push({text}),
    write:async items=>{const item=items[0];profileCopies.push({text:await(await item.getType('text/plain')).text(),html:await(await item.getType('text/html')).text()});}
   }});});
   for(const format of ['excel','word']){
    await picker().locator(`[data-copy-format][value="${format}"]`).check();
    for(const [cell,expected] of [[name,nameMatrix[0][0]],[row(10).locator('[data-column-key="row_number"] [data-column-value]'),'1']]){
     await cell.click();const copyCount=await page.evaluate(()=>profileCopies.length);await picker().locator('[data-table-copy]').click();
     await page.waitForFunction(count=>profileCopies.length>count,copyCount);
     assert.equal(await page.evaluate(()=>profileCopies.at(-1).text),expected);
     if(format==='word')assert.doesNotMatch(await page.evaluate(()=>profileCopies.at(-1).html),/svg|Відкрити анкету|person_full_info/);
    }
   }
   await visit('/person-positions?occupancy=occupied&sort_by=position_number&direction=desc');
   assert.equal(await row(20).locator('[data-column-key="row_number"] [data-column-value]').innerText(),'1');
   assert.equal(await row(20).locator('.staff-profile-link').getAttribute('href'),'/person_full_info/2');
   await Promise.all([page.waitForURL(base+'/person_full_info/2'),row(20).locator('.staff-profile-link').click()]);
   await visit('/person-positions');await page.evaluate(()=>localStorage.clear());await page.reload();
  });
  await scenario('one expanded assignment editor preserves drafts, cancellation and server errors',async()=>{
   await openAssignment(row(10));const date=row(10).locator('.person-assignment-form [name="on"]'),initial=await date.inputValue();
   await date.fill('2020-02-02');await openAssignment(row(20));assert.equal(await row(10).locator('[data-assignment-editor]').isHidden(),true);
   assert.equal(await row(10).locator('[data-assignment-draft]').isVisible(),true);
   await openAssignment(row(10));assert.equal(await date.inputValue(),'2020-02-02');
   page.once('dialog',d=>d.dismiss());await row(10).locator('[data-assignment-cancel]').click();assert.equal(await date.inputValue(),'2020-02-02');
   page.once('dialog',d=>d.accept());await row(10).locator('[data-assignment-cancel]').click();assert.equal(await row(10).locator('[data-assignment-editor]').isHidden(),true);
   await openAssignment(row(10));assert.equal(await date.inputValue(),initial);await row(10).locator('[data-assignment-close]').click();
   await row(10).locator('[data-column-key="unit_short"]').click();assert.equal(await row(10).locator('[data-assignment-editor]').isHidden(),true);
   await openAssignment(row(20));await row(20).locator('[data-person-label]').click();await row(20).locator('[data-person-option="1"]').click();
   await row(20).locator('[data-assignment-status]').filter({hasText:'зайнята'}).waitFor();
   assert.equal(await row(20).locator('[data-person-value]').inputValue(),'1');
   await openAssignment(row(10));await openAssignment(row(20));assert.match(await row(20).locator('[data-assignment-status]').innerText(),/зайнята/);
   page.once('dialog',d=>d.accept());await row(20).locator('[data-assignment-cancel]').click();
   assert.equal(await row(20).locator('[data-person-value]').inputValue(),'2');
   assert.match(await row(20).locator('[data-person-label]').innerText(),/Бета/);
  });
  await scenario('height changes every row, custom pixels persist, fonts and geometric scale remain independent',async()=>{
   await formatting();await picker().locator('[data-row-height]').selectOption('28');
   let heights=await table().locator('tbody tr').evaluateAll(rows=>rows.map(r=>r.getBoundingClientRect().height));assert.ok(heights.every(h=>Math.abs(h-28)<2),JSON.stringify(heights));
   await picker().locator('[data-row-height]').selectOption('custom');await picker().locator('[data-row-height-custom]').fill('83');await picker().locator('[data-row-height-custom]').dispatchEvent('change');
   await picker().locator('[data-table-font]').fill('18');await picker().locator('[data-table-font]').dispatchEvent('change');
   await picker().locator('[data-font-column]').selectOption('name_short');await picker().locator('[data-column-font]').fill('22');await picker().locator('[data-column-font]').dispatchEvent('change');
   const before=await table().locator('th[data-column-key="position_number"]').evaluate(n=>n.getBoundingClientRect().width);
   await picker().locator('[data-table-scale]').selectOption('125');
   const scaled=await table().locator('th[data-column-key="position_number"]').evaluate(n=>n.getBoundingClientRect().width);assert.ok(Math.abs(scaled-before*1.25)<2);
   heights=await table().locator('tbody tr').evaluateAll(rows=>rows.map(r=>r.getBoundingClientRect().height));assert.ok(heights.every(h=>Math.abs(h-103.75)<2));
   assert.equal(await row(10).locator('[data-column-key="name_short"]').evaluate(n=>getComputedStyle(n).fontSize),'27.5px');
   const handle=table().locator('th[data-column-key="position_number"] [data-column-resize]');await handle.scrollIntoViewIfNeeded();const box=await handle.boundingBox();
   await page.mouse.move(box.x+4,box.y+10);await page.mouse.down();await page.mouse.move(box.x+54,box.y+10,{steps:5});await page.mouse.up();
   const width=await page.evaluate(()=>TableColumns.controllers.get('person-positions').state.widths.position_number);assert.ok(Math.abs(width-220)<2,String(width));
   await page.reload();heights=await table().locator('tbody tr').evaluateAll(rows=>rows.map(r=>r.getBoundingClientRect().height));assert.ok(heights.every(h=>Math.abs(h-103.75)<2));
   await formatting();await picker().locator('[data-table-scale]').selectOption('100');
   await picker().locator('[data-table-font]').fill('14');await picker().locator('[data-table-font]').dispatchEvent('change');
  });
  await scenario('multiple rows and columns, Ctrl toggle, Shift ranges, and native keyboard shortcuts',async()=>{
   await picker().locator('[data-selection-mode]').selectOption('rows');await row(10).locator('[data-column-key="unit_short"]').click();await row(30).locator('[data-column-key="unit_short"]').click({modifiers:['Shift']});
   let matrix=await controller();assert.equal(matrix.length,3);assert.equal(matrix[0].length,11);
   await row(20).locator('[data-column-key="unit_short"]').click({modifiers:['Control']});matrix=await controller();assert.ok(matrix[1].every(v=>v===''));
   await picker().locator('[data-selection-clear]').click();assert.equal(await table().locator('.table-cell-selected').count(),0);
   await picker().locator('[data-selection-mode]').selectOption('columns');await row(10).locator('[data-column-key="unit_short"]').click();await row(10).locator('[data-column-key="name_short"]').click({modifiers:['Control']});
   matrix=await controller();assert.equal(matrix.length,3);assert.equal(matrix[0].length,2);
   await picker().locator('[data-selection-mode]').selectOption('cells');await picker().locator('[data-selection-clear]').click();
   const menuSelect=async(key,modifiers=[])=>{const header=table().locator(`th[data-column-key="${key}"]`);await header.locator('[data-bs-toggle="dropdown"]').click();await header.locator('[data-column-select]').click({modifiers});};
   await menuSelect('unit_short');await menuSelect('name_short',['Control']);assert.equal((await controller())[0].length,2);
   await menuSelect('name_nominative',['Shift']);assert.equal((await controller())[0].length,2);
   await picker().locator('[data-selection-clear]').click();
  });
  await scenario('local fills follow stable positions through sorting and copying contains complete values only',async()=>{
   await row(10).locator('[data-column-key="name_short"]').click();await formatting();await picker().locator('[data-cell-fill="#fff3cd"]').click();
   assert.equal(await row(10).locator('[data-column-key="name_short"]').getAttribute('data-user-fill'),'');
   const matrix=await controller();assert.deepEqual(matrix,[['Водій']]);
   await page.goto(base+'/person-positions?sort_by=position_number&direction=desc');
   assert.equal(await table().locator('tbody tr').first().getAttribute('data-row-key'),'position:3');
   assert.equal(await row(10).locator('[data-column-key="name_short"]').evaluate(n=>n.style.getPropertyValue('--table-user-fill')),'#fff3cd');
   assert.equal(await row(20).locator('[data-column-key="name_short"]').getAttribute('data-user-fill'),null);
   await row(10).locator('[data-column-key="name_short"]').click();await formatting();await picker().locator('[data-cell-fill=""]').click();
   assert.equal(await row(10).locator('[data-column-key="name_short"]').getAttribute('data-user-fill'),null);
  });
  await scenario('people reuse presets, drag, widths, selection and independent appearance state',async()=>{
   await visit('/persons');assert.equal(await page.locator('.app-navigation [aria-current="page"]').innerText(),'Люди');
   assert.equal(await table().locator('th:visible').count(),7);assert.equal(await table().locator('tbody tr').first().evaluate(n=>n.getBoundingClientRect().height),40);
   await table().locator('thead th[data-column-key="name"]').dragTo(table().locator('thead th[data-column-key="surname"]'),{sourcePosition:{x:12,y:10},targetPosition:{x:12,y:10}});
   assert.deepEqual((await table().locator('thead th:visible').evaluateAll(nodes=>nodes.map(n=>n.dataset.columnKey))).slice(0,3),['person_id','name','surname']);
   await page.waitForTimeout(220);
   await picker().locator('.column-toolbar > [data-preset-create]').click();const modal=picker().locator('[data-preset-save-modal]');await modal.locator('[data-preset-name]').fill('Люди');await modal.locator('[type=submit]').click();await modal.waitFor({state:'hidden'});
   await picker().locator('[data-column-toggle]').click();await picker().locator('[data-visibility-tree] [data-column-choice="tax_number"]').uncheck();await picker().locator('[data-column-apply]').click();
   assert.equal(await table().locator('th[data-column-key="tax_number"]').isVisible(),false);await picker().locator('[data-preset-apply]').click();assert.equal(await table().locator('th[data-column-key="tax_number"]').isVisible(),true);
   await formatting();await picker().locator('[data-row-height]').selectOption('64');
   await page.locator('[data-row-key="person:1"] [data-column-key="surname"]').click();const matrix=await controller();assert.deepEqual(matrix,[['Альфа']]);
   await picker().locator('[data-cell-fill="#d1e7dd"]').click();await page.goto(base+'/persons?sort_by=id&direction=desc');
   assert.equal(await page.locator('[data-row-key="person:1"] [data-column-key="surname"]').getAttribute('data-user-fill'),'');
   assert.equal(await table().locator('tbody tr').first().evaluate(n=>n.getBoundingClientRect().height),64);
   await visit('/person-positions');assert.ok(Math.abs(await row(10).evaluate(n=>n.getBoundingClientRect().height)-83)<2);
  });
  await scenario('mirage profiles have separate real links while the official position stays vacant',async()=>{
   const response=await context.request.post(base+'/personnel/mirages',{form:{person_id:'1',position_id:'3',note:'Тестовий план'}});assert.equal(response.status(),200);
   await page.reload();
   assert.match(await row(30).locator('.assignment-summary').innerText(),/Вакантна/);
   assert.match(await row(30).locator('.assignment-mirage').innerText(),/Міраж/);
   assert.equal(await row(30).locator('.assignment-mirage a').getAttribute('href'),'/person_full_info/1');
   assert.equal(await row(30).locator('[data-column-key="row_number"] a').count(),0);
  });
  await scenario('many-row viewport has a bottom scrollbar, sticky headers and unclipped interactive menus',async()=>{
   await context.request.post(base+'/_column-test/many-positions');await visit('/person-positions');
   const viewport=page.locator('.table-viewport');assert.equal(await table().locator('tbody tr').count(),123);
   const geometry=await viewport.evaluate(n=>({height:n.clientHeight,total:n.scrollHeight,width:n.clientWidth,wide:n.scrollWidth}));assert.ok(geometry.total>geometry.height);assert.ok(geometry.wide>geometry.width);
   await viewport.evaluate(n=>{n.scrollTop=1200;n.scrollLeft=0;});
   const top=await viewport.evaluate(n=>n.getBoundingClientRect().top);const header=table().locator('th[data-column-key="unit_short"]');const box=await header.boundingBox();assert.ok(Math.abs(box.y-top)<3);
   await header.locator('[data-bs-toggle="dropdown"]').click();const menu=page.locator('[data-filter-key="unit_short"]');await menu.waitFor({state:'visible'});
   assert.equal(await menu.evaluate(n=>n.matches(':popover-open')),true);const rect=await menu.boundingBox();assert.ok(rect.y>=0&&rect.y+rect.height<=1000);
   await menu.locator('.filter-search').fill('Перший');await menu.locator('input[value="Перший"]').check();
   await Promise.all([page.waitForURL(url=>url.searchParams.get('unit_short')==='Перший'),menu.locator('.apply-filter').click()]);
   assert.equal(await table().locator('tbody tr').count(),2);
  });
  await scenario('mobile controls fit the page and invalid legacy appearance falls back safely',async()=>{
   await page.setViewportSize({width:390,height:844});await visit('/person-positions');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await picker().locator('[data-column-toggle]').click();const bounds=await picker().locator('.column-visibility-menu').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390);
   await page.keyboard.press('Escape');
   await page.evaluate(()=>localStorage.setItem('project2:table-appearance:person-positions','invalid JSON'));await page.reload();
   const height=await row(10).evaluate(n=>n.getBoundingClientRect().height);assert.ok(Math.abs(height-40)<2,String(height));
   assert.deepEqual(errors,[]);
   await page.screenshot({path:'/tmp/project2-workspace-mobile.png'});
  });
 }finally{await page.close();}
};

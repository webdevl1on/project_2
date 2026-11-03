const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const setup=await context.request.post(base+'/_column-test/journal-snapshot');assert.equal(setup.status(),200);const fixture=await setup.json();
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const table=page.locator('.event-timeline'),row=id=>page.locator(`[data-journal-person-id="${id}"]`);
 const check=async(name,fn)=>{await fn();console.log('PASS journal snapshot: '+name);};
 try{
 await page.setViewportSize({width:1440,height:1000});
 await check('staff date and event period are independent across a version boundary and browser history',async()=>{
  await page.goto(base+'/events?as_of=2026-10-10&start=2026-10-01&end=2026-11-03');
  assert.equal(await page.locator('[data-journal-person-id]').count(),2);assert.equal(await row(3).count(),0);
  for(const key of ['row_number','position_number','position_short'])await page.locator(`[data-journal-column="${key}"]`).check();
  assert.equal((await row(1).locator('[data-column-key=position_number]').textContent()).trim(),'27');assert.equal((await row(1).locator('[data-column-key=unit]').textContent()).trim(),'Другий');
  assert.equal(await row(1).locator('.event-tone-vacation').count(),11);
  await Promise.all([page.waitForURL(u=>u.searchParams.get('as_of')==='2026-10-09'),page.locator('[data-staff-day="-1"]').click()]);
  assert.equal((await row(1).locator('[data-column-key=position_number]').textContent()).trim(),'15');assert.equal(await row(1).locator('.event-tone-vacation').count(),11);assert.equal(new URL(page.url()).searchParams.get('end'),'2026-11-03');
  await Promise.all([page.waitForURL(u=>u.searchParams.get('as_of')===fixture.today),page.locator('[data-staff-today]').click()]);
  await page.goBack();assert.equal(new URL(page.url()).searchParams.get('as_of'),'2026-10-09');await page.goForward();assert.equal(new URL(page.url()).searchParams.get('as_of'),fixture.today);
  await Promise.all([page.waitForURL(u=>u.searchParams.get('as_of')==='1999-12-31'),page.locator('[data-exact-date-for=as_of]').fill('31.12.1999')]);assert.equal(await page.locator('[data-journal-person-id]').count(),0);assert.ok((await table.textContent()).includes('немає офіційних призначень'));
  await Promise.all([page.waitForURL(u=>u.searchParams.get('as_of')==='2000-01-01'),page.locator('[data-staff-day="1"]').click()]);assert.equal(await page.locator('[data-journal-person-id]').count(),2);
 });
 await check('shared header menus search, multi-select, cascade and retain URL sorting and state',async()=>{
  await page.goto(base+'/events?as_of=2026-10-10&start=2026-10-01&end=2026-11-03');
  const header=table.locator('th[data-column-key=unit]');await header.locator('[data-bs-toggle]').click();const menu=header.locator('[data-journal-filter-key]');
  await menu.locator('.filter-search').fill('Другий');assert.equal(await menu.locator('.filter-option:visible').count(),1);await menu.locator('.select-all-filter').click();
  await Promise.all([page.waitForURL(u=>u.searchParams.has('jf_unit')),menu.locator('.apply-filter').click()]);assert.equal(await page.locator('[data-journal-person-id]').count(),1);assert.ok(await row(1).count());
  const name=table.locator('th[data-column-key=name]');await name.locator('[data-bs-toggle]').click();const nameMenu=name.locator('[data-journal-filter-key]');assert.equal(await nameMenu.locator('input[type=checkbox]').count(),1);
  await nameMenu.locator('.select-all-filter').click();await Promise.all([page.waitForURL(u=>u.searchParams.has('jf_name')),nameMenu.locator('.apply-filter').click()]);
  await name.locator('[data-bs-toggle]').click();await Promise.all([page.waitForURL(u=>u.searchParams.get('direction')==='desc'),name.locator('[data-sort-direction=desc]').click()]);
  assert.ok(new URL(page.url()).searchParams.has('jf_unit'));await page.reload();assert.equal(await page.locator('[data-journal-person-id]').count(),1);assert.equal(new URL(page.url()).searchParams.get('as_of'),'2026-10-10');
  await header.locator('[data-bs-toggle]').click();await menu.locator('.filter-search').fill('');await menu.locator('.select-all-filter').click();await Promise.all([page.waitForURL(u=>u.searchParams.getAll('jf_unit').length===2),menu.locator('.apply-filter').click()]);assert.equal(await page.locator('[data-journal-person-id]').count(),1); // name filter still active
  await page.getByRole('link',{name:'Скинути',exact:true}).click();const day=table.locator('th[data-column-key="date:2026-10-05:2026-10-05"]');await day.scrollIntoViewIfNeeded();await day.locator('[data-bs-toggle]').click();const days=day.locator('[data-journal-filter-key]');await days.locator('.filter-search').fill('відпустка');await days.locator('.select-all-filter').click();await Promise.all([page.waitForURL(u=>u.searchParams.has('jf_date:2026-10-05:2026-10-05')),days.locator('.apply-filter').click()]);assert.equal(await page.locator('[data-journal-person-id]').count(),1);assert.ok(await row(1).count());
 });
 await check('text selection is native, preserves the sidebar and allows Ctrl+C and browser context menu',async()=>{
  await page.goto(base+'/events?as_of=2026-10-10&start=2026-10-01&end=2026-10-31');await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:base});
  assert.equal(await page.locator('[data-selection-mode]').inputValue(),'text');const text=row(1).locator('.event-person-text'),before=await page.locator('[data-journal-person]').textContent();
  const bounds=await text.evaluate(el=>{const r=document.createRange();r.setStart(el.firstChild,1);r.setEnd(el.firstChild,12);const b=r.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height};});
  await page.mouse.move(bounds.x+1,bounds.y+bounds.h/2);await page.mouse.down();await page.mouse.move(bounds.x+bounds.w-1,bounds.y+bounds.h/2,{steps:8});await page.mouse.up();const selected=await page.evaluate(()=>getSelection().toString());assert.ok(selected.length>4);
  assert.equal(await table.locator('.table-cell-selected').count(),0);assert.equal(await page.locator('[data-journal-person]').textContent(),before);await page.keyboard.press('Control+c');assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),selected);
  await page.evaluate(()=>{window.contextPrevented=null;document.addEventListener('contextmenu',e=>{window.contextPrevented=e.defaultPrevented;});});await text.click({button:'right'});assert.equal(await page.evaluate(()=>window.contextPrevented),false);await page.keyboard.press('Escape');
 });
 await check('cell ranges and columns reuse TableSelection and Excel/Word copy without truncation',async()=>{
  await page.evaluate(()=>{window.copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>copied.push({text}),write:async items=>copied.push({text:await(await items[0].getType('text/plain')).text(),html:await(await items[0].getType('text/html')).text()})}});});
  await page.locator('[data-selection-mode]').selectOption('cells');const a=await row(1).locator('[data-column-key=name]').boundingBox(),b=await row(2).locator('[data-column-key=unit]').boundingBox();
  await page.mouse.move(a.x+10,a.y+10);await page.mouse.down();await page.mouse.move(b.x+20,b.y+8,{steps:8});await page.mouse.up();assert.equal(await table.locator('.table-cell-selected').count(),4);await page.keyboard.press('Control+c');await page.waitForFunction(()=>copied.length===1);assert.ok((await page.evaluate(()=>copied[0].text)).includes(fixture.name));
  await page.locator('[data-copy-format][value=word]').check();await page.locator('[data-table-copy]').click();await page.waitForFunction(()=>copied.some(item=>item.html));assert.ok((await page.evaluate(()=>copied.at(-1).html)).includes(fixture.name));
  const header=table.locator('th[data-column-key=name]');await header.locator('[data-bs-toggle]').click();await header.locator('[data-journal-select-column]').click();assert.equal(await table.locator('.table-cell-selected').count(),2);await page.locator('[data-table-copy]').click();assert.ok((await page.evaluate(()=>copied.at(-1).text)).includes(fixture.name));
  await page.locator('[data-journal-column=position_short]').check();
 });
 await check('wrap increases height without changing widths or values and persists with drag, scale and export',async()=>{
  const role=row(1).locator('[data-column-key=position_short]');await role.scrollIntoViewIfNeeded();const before=await role.boundingBox(),value=await role.textContent();await page.locator('[data-journal-wrap]').check();const after=await role.boundingBox();assert.ok(after.height>before.height);assert.ok(Math.abs(after.width-before.width)<1);assert.equal(await role.textContent(),value);
  await page.reload();assert.equal(await page.locator('[data-journal-wrap]').isChecked(),true);assert.equal(await page.locator('[data-selection-mode]').inputValue(),'columns');
  await page.locator('[name=scale][value=week]').check();await Promise.all([page.waitForURL(u=>u.searchParams.get('scale')==='week'),page.getByRole('button',{name:'Застосувати',exact:true}).click()]);assert.equal(await page.locator('[data-journal-wrap]').isChecked(),true);assert.equal(new URL(page.url()).searchParams.get('as_of'),'2026-10-10');
  const download=page.waitForEvent('download');await page.locator('[data-journal-export]').click();const csv=require('node:fs').readFileSync(await(await download).path(),'utf8');assert.ok(csv.includes(fixture.name));assert.ok(csv.includes(value));assert.ok(!csv.includes('Гамма'));
  await page.screenshot({path:'/tmp/project2-journal-snapshot.png',fullPage:true});
 });
 await check('VLK creation uses a real standalone catalog entry and compact toolbar fits mobile',async()=>{
  await row(1).locator('button').click();await page.locator('[data-journal-add]').first().click();const modal=page.locator('#person-events-modal');await modal.locator('[data-event-form]').waitFor({state:'visible'});
  assert.equal(await modal.locator('[name=event_type_id] option').filter({hasText:'Вихідний'}).count(),0);const state=await(await context.request.get(base+'/persons/1/events')).json();const service=state.types.find(t=>t.code==='SERVICE'),vlk=state.types.find(t=>t.code==='VLK');
  await modal.locator('[name=event_type_id]').selectOption(String(service.id));assert.ok(await modal.locator('[name=event_subtype_id] option').filter({hasText:'Вихідний'}).count());await modal.locator('[name=event_type_id]').selectOption(String(vlk.id));assert.equal(await modal.locator('[name=event_subtype_id] option').count(),1);assert.ok((await modal.locator('[name=purpose]').locator('..').textContent()).includes('Мета/роль'));
  const purpose=modal.locator('[name=purpose]');await purpose.fill('Тестова мета / роль');await purpose.focus();await page.keyboard.press('Control+a');assert.deepEqual(await purpose.evaluate(e=>[e.selectionStart,e.selectionEnd]),[0,'Тестова мета / роль'.length]);await page.keyboard.press('Control+c');assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'Тестова мета / роль');await modal.locator('[data-exact-date-for=date_start]').fill('16.10.2026');const saved=page.waitForResponse(r=>r.url().endsWith('/persons/1/events')&&r.request().method()==='POST');await modal.getByRole('button',{name:'Зберегти подію',exact:true}).click();assert.equal((await saved).status(),200);await modal.locator('[data-event-form]').waitFor({state:'hidden'});const actual=await(await context.request.get(base+'/persons/1/events')).json();assert.ok(actual.events.some(e=>e.type_code==='VLK'&&e.purpose==='Тестова мета / роль'));
  await modal.getByRole('button',{name:'Закрити',exact:true}).click();await modal.waitFor({state:'hidden'});await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  for(const sel of ['[data-staff-today]','[data-month-step="-1"]','[data-journal-export]','[data-journal-add]'])assert.ok(await page.locator(sel).first().isVisible());await page.screenshot({path:'/tmp/project2-journal-snapshot-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
 });
 }finally{await page.close();}
};

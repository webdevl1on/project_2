const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const check=async(name,fn)=>{await fn();console.log('PASS event corrections: '+name);};
 const listing=async()=> (await context.request.get(base+'/persons/1/events')).json();
 const catalog=await listing(),kind=code=>String(catalog.types.find(t=>t.code===code).id);
 const created=await context.request.post(base+'/persons/1/events',{form:{event_type_id:kind('VACATION'),event_subtype_id:String(catalog.types.find(t=>t.code==='VACATION').subtypes.find(s=>s.code==='VACATION_ANNUAL').id),date_start:'2026-10-01',date_end:'2026-10-10'}});assert.equal(created.status(),200);
 const key=(await created.json()).event_id;
 const plan=await context.request.post(base+'/persons/1/events',{form:{event_type_id:kind('SERVICE'),date_start:'2099-01-01'}});assert.equal(plan.status(),200);const planId=(await plan.json()).event_id;
 const ids=()=>page.locator('[data-journal-person-id]').evaluateAll(rows=>rows.map(r=>Number(r.dataset.journalPersonId)));
 async function sort(value,direction){const button=page.locator(`[data-journal-sort="${value}"]`);await Promise.all([page.waitForURL(u=>u.searchParams.get('sort')===value&&u.searchParams.get('direction')===direction),button.click()]);}
 const modal=page.locator('#person-events-modal'),form=modal.locator('[data-event-form]');
 try{
  await page.setViewportSize({width:1440,height:1000});
  await check('all information headers sort with current row numbering and missing staff fields last',async()=>{
   await page.goto(base+'/events?start=2026-10-01&end=2026-10-14');
   for(const name of ['row_number','position_number','position_short'])await page.locator(`[data-journal-column="${name}"]`).check();
   await sort('name','desc');assert.deepEqual(await ids(),[3,2,1]);
   await sort('unit','asc');assert.equal(new URL(page.url()).searchParams.get('sort'),'unit');
   await sort('position_number','asc');assert.deepEqual(await ids(),[1,2,3]);await sort('position_number','desc');assert.deepEqual(await ids(),[2,1,3]);
   await sort('position_short','asc');assert.deepEqual(await ids(),[1,2,3]);
   await sort('date:2026-10-03:2026-10-03','asc');assert.deepEqual(await ids(),[1,2,3]);await sort('date:2026-10-03:2026-10-03','desc');assert.deepEqual(await ids(),[3,2,1]);
   assert.deepEqual(await page.locator('tbody [data-journal-extra=row_number]').allTextContents(),['1','2','3']);
   await Promise.all([page.waitForURL(u=>u.searchParams.get('start')==='2026-11-01'),page.locator('[data-month-step="1"]').click()]);
   assert.equal(new URL(page.url()).searchParams.get('sort'),'date:2026-10-03:2026-10-03');
  });
  await check('shared drag moves full columns, saves the order, and leaves number fixed and sorting untouched',async()=>{
   await page.goto(base+'/events?start=2026-10-01&end=2026-10-14');
   const table=page.locator('.event-timeline'),url=page.url();
   const source=table.locator('th[data-column-key=position_number]'),target=table.locator('th[data-column-key="date:2026-10-02:2026-10-02"]');
   await source.dragTo(target);await page.waitForTimeout(250);
   const keys=await table.locator('thead th').evaluateAll(headers=>headers.map(h=>h.dataset.columnKey));
   assert.equal(keys[0],'row_number');assert.ok(keys.indexOf('position_number')>keys.indexOf('date:2026-10-01:2026-10-01'));assert.equal(page.url(),url);
   for(const row of await table.locator('tbody tr').all())assert.deepEqual(await row.locator('td').evaluateAll(cells=>cells.map(c=>c.dataset.columnKey)),keys);
   assert.equal(await table.locator('th[data-column-key=row_number]').getAttribute('draggable'),'false');
   await table.locator('th[data-column-key=unit]').dragTo(table.locator('th[data-column-key=row_number]'));await page.waitForTimeout(250);
   assert.deepEqual(await table.locator('thead th').evaluateAll(headers=>headers.map(h=>h.dataset.columnKey)),keys);
   await page.reload();assert.deepEqual(await table.locator('thead th').evaluateAll(headers=>headers.map(h=>h.dataset.columnKey)),keys);
   const download=page.waitForEvent('download');await page.locator('[data-journal-export]').click();const csv=require('node:fs').readFileSync(await (await download).path(),'utf8');const header=csv.split('\r\n')[0].split(';');assert.equal(header[0].replace(/^[\uFEFF\"]+|\"$/g,''),'№');assert.ok(header.findIndex(value=>value.includes('№ посади'))>header.findIndex(value=>value.includes('01.10.2026')));
   const resize=page.locator('.event-name-resizer');await resize.focus();await page.keyboard.press('ArrowRight');const width=(await page.locator('.event-person-heading').boundingBox()).width;await page.reload();assert.ok(Math.abs((await page.locator('.event-person-heading').boundingBox()).width-width)<2);
  });
  await check('summary identifies the selected person and exact interval above unchanged day totals',async()=>{
   await page.locator('[data-journal-person-id="1"] .event-person-cell button').click();
   assert.equal(await page.locator('[data-journal-summary-title]').textContent(),'Підсумок: Альфа Т.');
   assert.ok((await page.locator('[data-journal-period]').textContent()).includes('01.10.2026'));assert.ok((await page.locator('[data-journal-period]').textContent()).includes('14.10.2026'));
   assert.ok((await page.locator('[data-journal-summary]').textContent()).includes('10 дн.'));
  });
  await check('type correction requires explicit confirmation, cancel keeps the draft, then history retains the same id',async()=>{
   await page.locator(`[data-journal-event-id="${key}"] button[aria-label="Редагувати подію"]`).click();await form.waitFor({state:'visible'});
   await form.locator('[name=event_type_id]').selectOption(kind('BUSINESS_TRIP'));assert.equal(await form.locator('[name=event_subtype_id]').inputValue(),'');
   await form.locator('[name=event_subtype_id]').selectOption(String(catalog.types.find(t=>t.code==='BUSINESS_TRIP').subtypes.find(s=>s.code==='BUSINESS_TRIP_MISSION').id));
   await form.locator('[name=note]').fill('Чернетка виправлення');
   let writes=0;const track=request=>{if(request.method()==='POST'&&request.url().endsWith('/events/'+key))writes++;};page.on('request',track);
   await form.getByRole('button',{name:'Зберегти подію',exact:true}).click();await modal.locator('[data-event-type-confirm]').waitFor({state:'visible'});assert.equal(writes,0);
   assert.ok((await modal.locator('[data-event-type-confirm-text]').textContent()).includes('«Відпустка» на «Відрядження»'));
   await modal.locator('[data-event-type-no]').click();assert.equal(await form.isVisible(),true);assert.equal(await form.locator('[name=note]').inputValue(),'Чернетка виправлення');assert.equal(await form.locator('[name=event_type_id]').inputValue(),kind('BUSINESS_TRIP'));
   await form.getByRole('button',{name:'Зберегти подію',exact:true}).click();const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/events/'+key));await modal.locator('[data-event-type-yes]').click();assert.equal((await response).status(),200);await form.waitFor({state:'hidden'});page.off('request',track);
   const value=(await listing()).events.find(e=>e.event_id===key);assert.equal(value.type_code,'BUSINESS_TRIP');assert.equal(value.corrections.length,1);assert.equal(value.corrections[0].before.type_name,'Відпустка');
   await modal.getByRole('button',{name:'Закрити',exact:true}).click();await modal.waitFor({state:'hidden'});await page.locator('[data-journal-person-id="1"] .event-tone-trip').first().waitFor();
  });
  await check('annulment preserves reason on failure, leaves other facts unchanged, and remains in a collapsed read-only archive',async()=>{
   await page.locator(`[data-journal-event-id="${key}"]`).getByRole('button',{name:'Анулювати',exact:true}).click();
   const annulForm=modal.locator('[data-event-annul-form]');await annulForm.waitFor({state:'visible'});
   await annulForm.getByRole('button',{name:'Підтвердити анулювання',exact:true}).click();assert.equal(await annulForm.locator('[name=reason]').evaluate(e=>e.validity.valueMissing),true);
   await annulForm.locator('[name=reason]').fill('Помилкове внесення');await page.route(`**/persons/1/events/${key}/annul`,route=>route.abort('failed'));
   await annulForm.getByRole('button',{name:'Підтвердити анулювання',exact:true}).click();await annulForm.locator('[data-event-annul-error]').filter({hasText:'Причину збережено'}).waitFor();assert.equal(await annulForm.locator('[name=reason]').inputValue(),'Помилкове внесення');await page.unroute(`**/persons/1/events/${key}/annul`);
   const response=page.waitForResponse(r=>r.url().endsWith(`/events/${key}/annul`)&&r.request().method()==='POST');await annulForm.getByRole('button',{name:'Підтвердити анулювання',exact:true}).click();assert.equal((await response).status(),200);await annulForm.waitFor({state:'hidden'});
   const state=await listing();assert.equal(state.annulled.length,1);assert.equal(state.annulled[0].event_id,key);assert.equal(state.annulled[0].corrections.length,2);assert.equal(state.events.find(r=>r.event_id===planId).date_end,null);
   const archived=modal.locator('[data-event-annulled-archive]');assert.equal(await archived.getAttribute('open'),null);await archived.locator('summary').first().click();assert.equal(await archived.locator('[data-event-edit]').count(),0);assert.ok((await archived.textContent()).includes('Помилкове внесення'));
   await modal.getByRole('button',{name:'Закрити',exact:true}).click();await modal.waitFor({state:'hidden'});await page.locator('[data-journal-events] [data-event-annulled-archive]').waitFor();
   assert.equal(await page.locator(`[data-journal-event-id="${key}"]`).count(),0);await page.reload();const sidebar=page.locator('[data-journal-events] [data-event-annulled-archive]');assert.equal(await sidebar.getAttribute('open'),null);await sidebar.locator('summary').click();assert.ok((await sidebar.textContent()).includes('Анульовано'));
   assert.equal((await context.request.delete(base+'/persons/1/events/'+key)).status(),405);assert.deepEqual(errors,[]);
  });
 }finally{await page.close();}
};

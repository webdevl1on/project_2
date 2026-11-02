const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const check=async(name,fn)=>{await fn();console.log('PASS event lifecycle: '+name);};
 const listing=async pid=>(await context.request.get(`${base}/persons/${pid}/events`)).json();
 const catalog=await listing(1),kind=code=>String(catalog.types.find(t=>t.code===code).id);
 const modal=page.locator('#person-events-modal'),form=modal.locator('[data-event-form]');
 const date=name=>form.locator(`[data-exact-date-for="${name}"]`);
 const submit=async()=>{const response=page.waitForResponse(r=>r.url().includes('/persons/1/events')&&r.request().method()==='POST');await form.getByRole('button',{name:'Зберегти подію',exact:true}).click();assert.equal((await response).status(),200);await form.waitFor({state:'hidden'});};
 try{
  await check('open vacation retains planned and actual ends separately and blocks base service after its due date',async()=>{
   await page.goto(base+'/events?start=2026-10-01&end=2026-10-14&person_id=1');
   await page.locator('[data-journal-add]').first().click();await form.waitFor({state:'visible'});
   await form.locator('[name=event_type_id]').selectOption(kind('VACATION'));
   await form.locator('[name=event_subtype_id]').selectOption(String(catalog.types.find(t=>t.code==='VACATION').subtypes.find(s=>s.code==='VACATION_ANNUAL').id));
   await date('date_start').fill('01.10.2026');await date('planned_end').fill('10.10.2026');await submit();
   const record=(await listing(1)).events[0];assert.equal(record.planned_end,'2026-10-10');assert.equal(record.date_end,null);assert.equal(record.duration,null);assert.equal(record.completion_confirmed,false);
   await page.locator('[data-journal-person-id="1"] .event-tone-conflict').first().waitFor();
   assert.ok((await page.locator('[data-journal-person-id="1"]').textContent()).includes('Основна'));
   await modal.getByRole('button',{name:'Закрити',exact:true}).click();await modal.waitFor({state:'hidden'});
  });
  await check('explicit return prefills the planned date, retains invalid drafts, and accepts a different actual date',async()=>{
   await page.locator('[data-journal-events] button').first().click();await form.waitFor({state:'visible'});
   await modal.locator('[data-event-cancel]').click();
   await modal.locator('[data-event-confirm]').first().click();
   assert.equal(await date('date_end').inputValue(),'10.10.2026');assert.equal(await form.locator('[name=completion_confirmed]').isChecked(),true);
   await date('date_end').fill('30.09.2026');await form.getByRole('button',{name:'Зберегти подію',exact:true}).click();
   assert.equal(await date('date_end').getAttribute('aria-invalid'),'true');assert.equal(await date('date_start').inputValue(),'01.10.2026');
   await date('date_end').fill('12.10.2026');await submit();
   const record=(await listing(1)).events[0];assert.equal(record.date_end,'2026-10-12');assert.equal(record.duration,12);assert.equal(record.planned_end,'2026-10-10');
   await modal.getByRole('button',{name:'Закрити',exact:true}).click();await modal.waitFor({state:'hidden'});
   await page.locator('[data-journal-person-id="1"] .event-tone-service').first().waitFor();
  });
  await check('optional staff fields and name drag resize persist through reload and keep full text',async()=>{
   for(const name of ['row_number','position_number','position_short'])await page.locator(`[data-journal-column="${name}"]`).check();
   const row=page.locator('[data-journal-person-id="1"]');assert.equal((await row.locator('[data-journal-extra=row_number]').textContent()).trim(),'1');assert.equal((await row.locator('[data-journal-extra=position_number]').textContent()).trim(),'10');
   const free=page.locator('[data-journal-person-id="3"]');assert.equal((await free.locator('[data-journal-extra=position_number]').textContent()).trim(),'');
   const heading=page.locator('.event-person-heading'),before=(await heading.boundingBox()).width,handle=page.locator('.event-name-resizer');let box=await handle.boundingBox();
   await page.mouse.move(box.x+4,box.y+10);await page.mouse.down();await page.mouse.move(box.x+104,box.y+10,{steps:6});await page.mouse.up();
   assert.ok((await heading.boundingBox()).width>before+70);
   box=await handle.boundingBox();await page.mouse.move(box.x+4,box.y+10);await page.mouse.down();await page.mouse.move(box.x-36,box.y+10,{steps:5});await page.mouse.up();
   const after=(await heading.boundingBox()).width;assert.ok(after<before+90);await page.reload();
   assert.ok(Math.abs((await page.locator('.event-person-heading').boundingBox()).width-after)<2);
   assert.equal(await page.locator('[data-journal-column=position_short]').isChecked(),true);assert.ok((await row.locator('.event-person-cell button').getAttribute('title')).includes('Альфа'));
   await page.locator('[data-journal-column=position_number]').uncheck();assert.equal(await row.locator('[data-journal-extra=position_number]').isVisible(),false);
  });
  await check('month navigation selects exact leap-year boundaries and preserves filters and scales',async()=>{
   await page.goto(base+'/events?start=2026-10-01&end=2026-10-14&search=Альфа&unit=Перший&scale=week&sort=unit&direction=desc');
   await Promise.all([page.waitForURL(u=>u.searchParams.get('start')==='2026-09-01'),page.locator('[data-month-step="-1"]').click()]);
   let url=new URL(page.url());assert.equal(url.searchParams.get('end'),'2026-09-30');assert.equal(url.searchParams.get('unit'),'Перший');assert.equal(url.searchParams.get('scale'),'week');assert.equal(url.searchParams.get('direction'),'desc');
   await page.locator('[data-month-title]').click();await page.locator('[data-month-select]').selectOption('2');await page.locator('[data-month-year]').fill('2024');
   await Promise.all([page.waitForURL(u=>u.searchParams.get('start')==='2024-02-01'),page.locator('[data-month-apply]').click()]);
   assert.equal(new URL(page.url()).searchParams.get('end'),'2024-02-29');assert.equal(await page.locator('[data-exact-date-for=end]').inputValue(),'29.02.2024');
  });
  await check('future plans are dashed, never close current facts, and control issues are separate from medicine',async()=>{
   assert.equal((await context.request.post(base+'/persons/3/events',{form:{event_type_id:kind('HOSPITAL'),date_start:'2026-10-01'}})).status(),200);
   assert.equal((await context.request.post(base+'/persons/3/events',{form:{event_type_id:kind('VACATION'),date_start:'2099-01-01',planned_end:'2099-01-10'}})).status(),200);
   const records=(await listing(3)).events;assert.equal(records.length,2);assert.equal(records.find(r=>r.type_code==='HOSPITAL').date_end,null);assert.equal(records.find(r=>r.type_code==='VACATION').mirage,true);
   await page.goto(base+'/events?start=2099-01-01&end=2099-01-02&person_id=3');assert.ok(await page.locator('[data-journal-person-id="3"] .event-mirage').count());
   await page.goto(base+'/events/problems');assert.equal(await page.locator('[data-event-problem]').count(),1);assert.ok((await page.locator('[data-event-problem]').textContent()).includes('Лікування понад 15'));
   assert.ok((await page.locator('main').textContent()).includes('немає типу або підтипу ВЛК'));
   await page.reload();assert.equal(await page.locator('[data-event-problem]').count(),1);assert.deepEqual(errors,[]);
  });
 }finally{await page.close();}
};

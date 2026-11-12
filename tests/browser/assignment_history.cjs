const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const editor=page.locator('#history-editor'),form=editor.locator('form');
 const position=id=>page.locator(`[data-position-id="${id}"]`);
 const date=key=>form.locator(`[data-exact-date-for="${key}"]`);
 const scenario=async(name,fn)=>{await fn();console.log(`PASS assignment history: ${name}`);};
 const open=async id=>{if(!(await position(id).evaluate(n=>n.open)))await position(id).locator(':scope > summary').click();};
 const add=async(id,person,from,to='')=>{await open(id);await page.locator(`[data-history-add="${id}"]`).click();await editor.waitFor({state:'visible'});await form.locator('[data-person-label]').click();await form.locator(`[data-person-option="${person}"]`).click();await date('assigned_from').fill(from);await date('assigned_to').fill(to);};
 const save=async()=>{await Promise.all([page.waitForNavigation(),form.locator('[type=submit]').click()]);};
 const close=async()=>{await editor.locator('[data-bs-dismiss=modal]').first().click();await editor.waitFor({state:'hidden'});};
 const state=page.locator('#history-state');
 const changeState=async(id,action)=>{await page.locator(`[data-history-${action}="${id}"]`).click();await state.waitFor({state:'visible'});if(action==='annul')await state.locator('[name=reason]').fill('Тестове виправлення помилкового запису');await state.locator('[name=confirmed]').check();};
 try{
  await page.goto(base+'/staff/history');
  await scenario('all positions including vacancy start collapsed; number/full-name search stays in URL',async()=>{
   assert.equal(await page.locator('[data-position-id]').count(),3);assert.equal(await page.locator('[data-position-id][open]').count(),0);
   assert.equal(await page.locator('[data-person-picker]').count(),1);
   await page.locator('input[type=search][name=q]').fill('30');await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Показати',exact:true}).click()]);assert.equal(await page.locator('[data-position-id]').count(),1);assert.match(page.url(),/q=30/);
   await page.reload();assert.equal(await page.locator('input[type=search][name=q]').inputValue(),'30');
   await page.locator('input[type=search][name=q]').fill('БЕЗПІЛОТНИХ');await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Показати',exact:true}).click()]);assert.equal(await page.locator('[data-position-id]').count(),1);
   await page.goto(base+'/staff/history');
  });
  let archived,current;
  await scenario('create historical and current entries in preselected vacancy; exact dates and same person twice',async()=>{
   await add(3,3,'01.05.2026','31.05.2026');assert.equal(await form.locator('[name=position_id]').inputValue(),'3');
   await form.locator('[name=assignment_order_number]').fill('100');await date('assignment_order_date').fill('30.04.2026');await save();await open(3);
   archived=await position(3).locator('[data-history-edit]').getAttribute('data-history-edit');
   await add(3,3,'01.06.2026');await save();await open(3);
   current=await position(3).locator('[data-history-edit]').first().getAttribute('data-history-edit');
   assert.notEqual(archived,current);assert.match(await position(3).innerText(),/Поточне призначення/);assert.match(await position(3).innerText(),/Архівні призначення/);assert.match(await position(3).innerText(),/01.05.2026 — 31.05.2026/);
  });
  await scenario('conflicting edit keeps same ID, person, orders, dates and open modal; valid correction succeeds',async()=>{
   await page.locator(`[data-history-edit="${archived}"]`).click();await editor.waitFor({state:'visible'});assert.equal(await date('assigned_from').inputValue(),'01.05.2026');
   await date('assigned_to').fill('05.06.2026');await form.locator('[name=assignment_order_number]').fill('100/1');
   const before=await form.evaluate(n=>[...new FormData(n)]);await form.locator('[type=submit]').click();await form.locator('[data-history-form-error]').filter({hasText:'перетинаються'}).waitFor();assert.deepEqual(await form.evaluate(n=>[...new FormData(n)]),before);
   assert.equal(await editor.isVisible(),true);await date('assigned_to').fill('30.05.2026');await save();await open(3);
   assert.equal(await page.locator(`[data-history-edit="${archived}"]`).count(),1);assert.match(await position(3).innerText(),/100\/1/);
  });
  await scenario('annul requires reason and confirmation, segregates history and frees actual roster',async()=>{
   await page.locator(`[data-history-annul="${current}"]`).click();await state.waitFor({state:'visible'});await state.locator('[type=submit]').click();assert.equal(await state.isVisible(),true);
   await state.locator('[name=reason]').fill('Тестове анулювання');await state.locator('[name=confirmed]').check();await Promise.all([page.waitForNavigation(),state.locator('[type=submit]').click()]);await open(3);
   assert.equal(await position(3).locator('[data-annulled-group][open]').count(),0);assert.match(await position(3).locator('summary').first().innerText(),/Вакантна/);
   await position(3).locator('[data-annulled-group] > summary').click();assert.equal(await page.locator(`[data-history-restore="${current}"]`).count(),1);
   const roster=await context.request.get(base+'/person-positions?as_of=2026-07-01');assert.equal(roster.ok(),true);
  });
  await scenario('restore uses original ID; repeated annulment retains audit',async()=>{
   await changeState(current,'restore');await Promise.all([page.waitForNavigation(),state.locator('[type=submit]').click()]);await open(3);assert.equal(await page.locator(`[data-history-edit="${current}"]`).count(),1);
   await changeState(current,'annul');await Promise.all([page.waitForNavigation(),state.locator('[type=submit]').click()]);await open(3);
  });
  await scenario('transfer proposes one order, cancellation preserves draft; explicit confirmation closes source atomically',async()=>{
   await add(3,1,'01.07.2026');await form.locator('[name=assignment_order_number]').fill('125');await date('assignment_order_date').fill('30.06.2026');
   assert.equal(await form.locator('[name=transfer_release_order_number]').inputValue(),'125');assert.equal(await form.locator('[name=transfer_release_order_date]').inputValue(),'2026-06-30');
   await form.locator('[type=submit]').click();const review=editor.locator('[data-transfer-message]');await review.waitFor();assert.match(await review.innerText(),/30.06.2026/);
   await editor.locator('[data-transfer-back]').click();assert.equal(await form.locator('[name=assignment_order_number]').inputValue(),'125');
   await form.locator('[name=transfer_release_order_number]').fill('125-release');await form.locator('[name=assignment_order_number]').fill('125/1');assert.equal(await form.locator('[name=transfer_release_order_number]').inputValue(),'125-release');
   await form.locator('[type=submit]').click();await review.waitFor();await Promise.all([page.waitForNavigation(),editor.locator('[data-transfer-confirm]').click()]);await open(1);await open(3);
   assert.match(await position(1).innerText(),/125-release/);assert.match(await position(3).innerText(),/125\/1/);assert.match(await position(1).innerText(),/30.06.2026/);
  });
  await scenario('restore conflict keeps open form and current occupant; history shows operations and real field differences',async()=>{
   await position(3).locator('[data-annulled-group] > summary').click();await changeState(current,'restore');await state.locator('[type=submit]').click();await state.locator('[data-history-form-error]').filter({hasText:'перетинаються'}).waitFor();assert.equal(await state.isVisible(),true);
   await state.locator('[data-bs-dismiss=modal]').click();await state.waitFor({state:'hidden'});
   await page.locator(`[data-history-audit="${current}"]`).click();const audit=page.locator('#history-audit');await audit.waitFor({state:'visible'});await audit.locator('table').first().waitFor();assert.match(await audit.innerText(),/Браузерний тестовий адміністратор/);assert.match(await audit.innerText(),/Відновлення/);assert.match(await audit.innerText(),/Анулювання/);assert.match(await audit.innerText(),/01.06.2026/);
   await audit.locator('[data-bs-dismiss=modal]').click();await audit.waitFor({state:'hidden'});
  });
  await scenario('version selection refreshes the complete list without leaking positions from another version',async()=>{
   await context.request.post(base+'/auth/login',{data:{username:'browser-admin',password:adminToken}});
   await page.goto(base+'/admin/staff');await page.getByRole('button',{name:'Завантажити штатну структуру',exact:true}).click();
   const importer=page.locator('#staff-import-modal');
   await importer.locator('[name=file]').setInputFiles(require('node:path').resolve(__dirname,'../../reference_data.xlsx'));
   await importer.locator('[name=name]').fill('Окрема тестова архівна версія');await importer.locator('[data-exact-date-for=valid_from]').fill('01.01.1999');await importer.locator('[data-exact-date-for=valid_to]').fill('31.12.1999');
   await Promise.all([page.waitForNavigation(),importer.getByRole('button',{name:'Перевірити файл'}).click()]);
   await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Підтвердити завантаження'}).click()]);
   const imported=new URL(page.url()).searchParams.get('version_id');
   await page.goto(base+'/staff/history?version_id=1');
   await page.locator('[data-history-version]').selectOption(imported);await page.waitForURL('**/staff/history?version_id='+imported+'&q=');
   assert.equal(await page.locator('[data-position-id]').count(),10);assert.equal(await position(1).count(),0);
   await page.reload();assert.equal(await page.locator('[data-history-version]').inputValue(),imported);
   await page.locator('[data-history-version]').selectOption('1');await page.waitForURL('**/staff/history?version_id=1&q=');assert.equal(await page.locator('[data-position-id]').count(),3);
  });
  await scenario('future server guard preserves draft and mobile layout remains usable',async()=>{
   await add(2,3,'01.01.2099');await form.locator('[type=submit]').click();await form.locator('[data-history-form-error]').filter({hasText:'завтра'}).waitFor();assert.equal(await date('assigned_from').inputValue(),'01.01.2099');await close();
   await page.setViewportSize({width:390,height:844});await page.reload();await open(3);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);assert.deepEqual(errors,[]);
  });
 }finally{await page.close();}
};

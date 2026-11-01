const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await context.request.get(base+'/auth/me');
  await page.goto(base+'/person_full_info/3#documents');
  const panel=page.locator('[data-document-panel]'),form=panel.locator('[data-document-form]'),editor=panel.locator('[data-document-editor]');
  await panel.locator('[data-document-content]').waitFor({state:'visible'});
  await panel.locator('[data-document-history]').check();assert.equal(await panel.locator('[data-document-archive]').isVisible(),false);await panel.locator('[data-document-history]').uncheck();
  assert.match((await panel.locator('[data-document-current-list] > [data-document-card] > summary').allTextContents()).slice(0,4).join('|'),/^Паспорт.*\|РНОКПП.*\|Військово-обліковий.*\|Свідоцтво про народження/);
  await panel.locator('[data-document-new]').click();
  assert.equal(await form.locator('[name=type] option').count(),8);
  await form.locator('[name=type]').selectOption('tax_number');
  assert.equal(await form.locator('[name=number]').getAttribute('readonly'),null);
  assert.equal(await form.getByRole('link',{name:'Редагувати облікові дані'}).count(),0);
  await form.locator('[name=type]').selectOption('other');await form.locator('[name=number]').fill('GUI-001');
  await form.locator('[data-exact-date-for=issued_date]').fill('31.10.2026');
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'}).catch(async e=>{console.log('DOCUMENT DIAG',await panel.locator('[data-document-message]').textContent(),await form.evaluate(n=>({valid:n.checkValidity(),invalid:[...n.querySelectorAll(':invalid')].map(x=>[x.name,x.value,x.validationMessage])})));throw e;});
  let card=panel.locator('[data-document-card]').filter({hasText:'GUI-001'});await card.evaluate(n=>n.open=true);
  assert.match(await card.innerText(),/31.10.2026/);assert.match(await card.innerText(),/Невідомо/);assert.match(await card.innerText(),/Копії не завантажені/);
  await card.getByRole('button',{name:'Редагувати',exact:true}).click();await form.locator('[name=number]').fill('GUI-002');
  // Server conflict keeps the editor and all user input.
  await page.route('**/persons/3/documents/*',async route=>{if(route.request().method()==='POST'&&route.request().headers()['content-type']?.includes('application/json'))return route.fulfill({status:409,json:{detail:'Тестовий конфлікт ревізії'}});return route.continue();});
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();await panel.locator('[data-document-message]').filter({hasText:'Тестовий конфлікт'}).waitFor();
  assert.equal(await form.locator('[name=number]').inputValue(),'GUI-002');assert.equal(await editor.isVisible(),true);
  await page.unroute('**/persons/3/documents/*');await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'});
  card=panel.locator('[data-document-card]').filter({hasText:'GUI-002'});await card.evaluate(n=>n.open=true);const oldId=await card.getAttribute('data-document-card');
  console.log('PASS documents GUI: server catalog, canonical tax field, create/edit and retained conflict draft');
  await card.locator('details').evaluate(n=>n.open=true);
  const upload=card.locator('form').filter({has:page.locator('input[type=file]')});
  for(const [name,mime,buffer,side] of [['front.pdf','application/pdf',Buffer.from('%PDF-1.7 synthetic'),'front'],['back.png','image/png',Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0WQAAAAASUVORK5CYII=','base64'),'back'],['extra.jpg','image/jpeg',Buffer.from([255,216,255,224,0,16]),'page']]){
   await upload.locator('[name=file]').setInputFiles({name,mimeType:mime,buffer});await upload.getByRole('button',{name:'Додати копію'}).click();
   await card.getByRole('link',{name}).waitFor();
  }
  assert.equal((await context.request.get(base+await card.getByRole('link',{name:'front.pdf'}).getAttribute('href'))).status(),200);
  assert.match(await card.innerText(),/Копії завантажені/);assert.match(await card.innerText(),/Фізична наявність: Невідомо/);
  await card.getByRole('button',{name:'Замінити документ'}).click();await form.locator('[name=number]').fill('GUI-003');await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'});
  assert.equal(await panel.locator('[data-document-card]').filter({hasText:'GUI-002'}).count(),0);await panel.locator('[data-document-history]').check();assert.equal(await panel.locator('[data-document-card]').filter({hasText:'GUI-002'}).count(),1);
  const archive=panel.locator('[data-document-archive]');assert.equal(await archive.isVisible(),true);assert.equal(await archive.locator(`[data-document-card="${oldId}"]`).count(),1);assert.equal(await panel.locator('[data-document-current-list]').locator(`[data-document-card="${oldId}"]`).count(),0);
  assert.equal(await panel.locator('[data-document-list]').evaluate(n=>n.querySelector('[data-document-current-list]').compareDocumentPosition(n.querySelector('[data-document-archive]')) & Node.DOCUMENT_POSITION_FOLLOWING),4);
  await panel.locator('[data-document-history]').uncheck();assert.equal(await archive.isVisible(),false);await panel.locator('[data-document-history]').check();
  const current=panel.locator('[data-document-current-list] [data-document-card]').filter({hasText:'GUI-003'});await current.evaluate(n=>n.open=true);page.once('dialog',d=>d.accept());await current.getByRole('button',{name:'Архівувати',exact:true}).click();await archive.locator('[data-document-card]').filter({hasText:'GUI-003'}).waitFor();assert.equal(await panel.locator('[data-document-current-list] [data-document-card]').filter({hasText:'GUI-003'}).count(),0);
  const oldCard=archive.locator(`[data-document-card="${oldId}"]`);await oldCard.evaluate(n=>n.open=true);await oldCard.locator('details').evaluate(n=>n.open=true);assert.equal(await oldCard.getByRole('link',{name:'front.pdf'}).count(),1);assert.match(await oldCard.innerText(),/31.10.2026/);
  console.log('PASS document archive: current first, separate lower block, toggle, explicit archive retains values and copies');
  await page.reload();await panel.locator('[data-document-content]').waitFor({state:'visible'});assert.equal(await panel.locator('[data-document-current-list] [data-document-card]').filter({hasText:'GUI-003'}).count(),0);await panel.locator('[data-document-history]').check();assert.equal(await panel.locator('[data-document-archive-list] [data-document-card]').filter({hasText:'GUI-003'}).count(),1);
  assert.equal(await panel.locator('[data-document-card="empty-passport"] [name=presence] option[value=NEVER_OBTAINED]').count(),0);
  assert.deepEqual(errors,[]);console.log('PASS documents GUI: multiple protected copies, independent states, replacement/history and reload');
  await panel.locator('[data-document-new]').click();await form.locator('[name=type]').selectOption('passport');
  await form.locator('[name=subtype]').selectOption('book');await form.locator('[name=series]').fill('АА');await form.locator('[name=number]').fill('123456');await form.locator('[name=issued_by]').fill('Тестовий орган');await form.locator('[name=issued_year]').fill('2015');
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'});
  const passport=panel.locator('[data-document-card]').filter({hasText:'123456'});await passport.evaluate(n=>n.open=true);assert.match(await passport.innerText(),/_\._\.2015/);
  await passport.getByRole('button',{name:'Редагувати',exact:true}).click();assert.equal(await form.locator('[name=issued_day]').inputValue(),'');assert.equal(await form.locator('[name=issued_year]').inputValue(),'2015');await panel.locator('[data-document-cancel]').click();
  await panel.locator('[data-document-new]').click();await form.locator('[name=type]').selectOption('driving_license');await form.locator('[name=number]').fill('DRIVE-001');await panel.locator('[data-driving-add]').click();await form.locator('[name=category]').selectOption('B');await form.locator('[data-driving-row] [data-exact-date-for=start_date]').fill('29.02.2024');
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'});
  const driving=panel.locator('[data-document-card]').filter({hasText:'DRIVE-001'});await driving.evaluate(n=>n.open=true);assert.match(await driving.innerText(),/Категорія B: 29.02.2024/);
  // Changing a dynamic type after invalid partial input must not retain a detached validator.
  await panel.locator('[data-document-new]').click();await form.locator('[name=type]').selectOption('passport');await form.locator('[name=issued_day]').fill('31');await form.locator('[name=issued_month]').fill('2');await form.locator('[name=type]').selectOption('other');assert.equal(await form.evaluate(n=>n.checkValidity()),true);await panel.locator('[data-document-cancel]').click();if(await panel.locator('[data-document-discard-modal]').isVisible())await panel.locator('[data-discard-confirm]').click();
  await page.goto(base+'/person_full_info/3#documents-'+oldId);await page.reload();
  const archived=panel.locator(`[data-document-card="${oldId}"]`);await archived.waitFor({state:'visible'});assert.equal(await archived.evaluate(n=>n.open),true);assert.equal(await panel.locator('[data-document-history]').isChecked(),true);assert.equal(new URL(page.url()).hash,'#documents-'+oldId);
  assert.deepEqual(errors,[]);console.log('PASS documents GUI: canonical passport preserves partial date; driving category has exact date; changing dynamic schema discards old validation; archived hash opens its card');
 }finally{await page.close();}
};

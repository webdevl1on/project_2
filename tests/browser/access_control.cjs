const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const setup=await context.request.post(base+'/_column-test/access/setup');assert.equal(setup.status(),200,await setup.text());const ids=await setup.json();
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const select='[data-access-user]',row=`[data-access-row="unit:${ids.unit}"]`;
 async function matrix(){return (await context.request.get(base+`/admin/access/data?user_id=${ids.user}`)).json();}
 async function save(changes){const state=await matrix();const r=await context.request.post(base+`/admin/access/users/${ids.user}/matrix`,{data:{revision:state.user.revision,changes,reason:'Synthetic browser policy'}});assert.equal(r.status(),200,await r.text());}
 async function login(request,username){const r=await request.post(base+'/auth/login',{data:{username,password:adminToken}});assert.equal(r.status(),200,await r.text());await require('./mfa_helpers.cjs').complete(request,base);}
 try{
  await page.goto(base+`/admin/access?user_id=${ids.user}`);await page.locator(row).count();
  await page.locator('[data-access-expand]').click();await page.locator(row).waitFor();
  await page.locator(row+' [data-rule-category=basic][data-rule-action=read]').selectOption('ALLOW');
  assert.equal(await page.locator(row+' [data-row-all]').evaluate(n=>n.indeterminate),true);
  await page.locator('[data-access-save] [name=reason]').fill('Погоджене базове читання');await page.locator('[data-access-save] button').click();await page.getByText('Матрицю збережено. Права перераховані на сервері.',{exact:true}).waitFor();
  assert.equal((await matrix()).manual.length,1);assert.equal(await page.locator(row+' [data-rule-category=basic][data-rule-action=read]').inputValue(),'ALLOW');
  const category=page.getByRole('button',{name:/Базова інформація/});await category.click();assert.equal(await page.locator(row+' [data-rule-category=basic]').count(),0);await category.click();assert.equal(await page.locator(row+' [data-rule-category=basic]').count(),2);
  await page.locator('[data-access-search]').fill('№10');assert.equal(await page.locator('[data-access-row]').count(),1);await page.locator('[data-access-search]').fill('');
  console.log('PASS ACL: server catalogue, tree and position search, tri-state matrix, atomic save, category collapse');
  const template=page.locator('[data-template-editor]');await template.locator('..').locator(':scope > summary').click();await template.locator('[name=name]').fill('ACL browser template');await template.locator('[data-capability="events:read"]').check();await template.locator('[name=reason]').fill('Synthetic template');await template.locator('button:not([type=button])').click();await page.getByText(/Шаблон збережено/).waitFor();const templateId=Number(await template.locator('[name=id]').inputValue());assert.ok(templateId>0);
  await template.locator('[name=name]').fill('ACL independent copy');await template.locator('[name=copy]').check();await template.locator('button:not([type=button])').click();await page.getByText('Шаблон збережено · ID '+(templateId+1),{exact:true}).waitFor();assert.notEqual(Number(await template.locator('[name=id]').inputValue()),templateId);
  const original=await (await context.request.get(base+`/admin/access/templates/${templateId}`)).json();assert.equal(original.name,'ACL browser template');
  console.log('PASS ACL: GUI template creation and independent copy preserve the original and refresh revision');
  const policy=page.locator('[data-position-policy]');await policy.locator('..').locator(':scope > summary').click();await policy.locator('[name=position_id]').selectOption(String(ids.positions[0]));await policy.locator('[data-capability="basic:read"]').check();await policy.locator('[name=reason]').fill('Approved synthetic baseline');await policy.locator('[name=confirmed]').check();await policy.locator('button:not([type=button])').click();await page.getByText(/Політику затверджено/).waitFor();
  const link=page.locator('[data-access-link]');await link.locator('..').locator(':scope > summary').click();await link.locator('[name=person_id]').fill('1');await link.locator('[name=reason]').fill('Link synthetic officer');await link.locator('button').click();await page.getByText('Зв’язок змінено; призначення не змінювалися.',{exact:true}).waitFor();await page.locator('[data-access-reviews]').getByRole('button',{name:'Завершити перевірку',exact:true}).waitFor();
  page.once('dialog',dialog=>dialog.accept('Effective grants checked'));await page.locator('[data-access-reviews]').getByRole('button',{name:'Завершити перевірку',exact:true}).click();await page.locator('[data-access-reviews]').getByText(/RESOLVED/).waitFor();
  console.log('PASS ACL: approved leadership policy, unique account-person link and explicit review decision use the real GUI');
  await page.locator(select).selectOption(String(ids.admin));await page.getByText('Admin має захищений повний предметний доступ.',{exact:true}).waitFor();assert.equal(await page.locator('[data-access-save] button').isDisabled(),true);
  await page.locator(select).selectOption(String(ids.master));await page.getByText(/Master: системні повноваження захищені/).waitFor();assert.equal(await page.locator('[data-access-save] button').isDisabled(),true);
  await page.locator(select).selectOption(String(ids.user));await page.locator('[data-access-save] button:enabled').waitFor();
  console.log('PASS ACL: protected Admin privileges and Master matrix cannot be changed by ordinary Admin');
  const user=await context.browser().newContext();try{
   await login(user.request,'acl-user');const u=await user.newPage();await u.goto(base+'/person_full_info/1');assert.match(await u.locator('body').innerText(),/Альфа Тест/);assert.doesNotMatch(await u.locator('body').innerText(),/0000000001|ACL-SECRET/);assert.equal(await u.locator('[data-document-panel],[data-medical-panel]').count(),0);
   assert.equal((await user.request.get(base+`/persons/1/documents/files/${ids.file}`)).status(),403);
   assert.equal((await user.request.get(base+'/admin/access')).status(),403);
   console.log('PASS ACL: User receives minimal permitted profile; denied categories, direct file IDs and management stay closed');
   await save([{scope_type:'unit',unit_id:ids.unit,category:'documents',action:'read',effect:'ALLOW'}]);
   assert.equal((await user.request.get(base+`/persons/1/documents/files/${ids.file}`)).status(),200);
   await u.goto(base+'/person_full_info/1');await u.locator('[data-document-panel]').locator('..').locator(':scope > summary').click();await u.getByText('ACL-SECRET-DOC',{exact:false}).first().waitFor();
   assert.equal(await u.locator('[data-document-new]:visible').count(),0);
   await save([{scope_type:'person',person_id:1,category:'documents',action:'read',effect:'DENY'}]);
   assert.equal((await user.request.get(base+`/persons/1/documents/files/${ids.file}`)).status(),403);
   console.log('PASS ACL: read-only documents and private files follow the same permission; personal DENY takes immediate precedence');
  }finally{await user.close();}
  await page.setViewportSize({width:390,height:844});await page.goto(base+`/admin/access?user_id=${ids.user}`);await page.locator('[data-access-expand]').click();await page.locator(row).waitFor();assert.equal(await page.locator('[data-access-matrix]').evaluate(n=>n.scrollWidth>n.clientWidth||n.parentElement.scrollWidth>n.parentElement.clientWidth),true);
  assert.equal((await context.request.get(base+'/persons/1/medical')).status(),200);
  assert.deepEqual(errors,[]);console.log('PASS ACL: narrow-screen matrix scrolls; Admin subject access remains available; no JavaScript errors');
 }finally{await page.close();}
};

const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const password='synthetic-new-browser-password';
 async function submit(form){await Promise.all([page.waitForNavigation(),form.locator('button').click()]);}
 async function signIn(username,secret){await context.clearCookies();const r=await context.request.post(base+'/auth/login',{data:{username,password:secret}});assert.equal(r.status(),200,await r.text());}
 async function create(username,role){
  await page.goto(base+'/admin/users/new');const form=page.locator('[data-account-form]');
  await form.locator('[name=username]').fill(username);await form.locator('[name=display_name]').fill('Тест '+username);
  await form.locator('[name=role]').selectOption(role);await form.locator('[name=password]').fill(password);await form.locator('[name=confirm_password]').fill(password);
  await submit(form);return Number(page.url().split('/').pop());
 }
 try{
  const promote=await context.request.post(base+'/_column-test/account-master');assert.equal(promote.status(),200);const master=(await promote.json()).id;
  await page.goto(base+'/admin');await page.getByRole('link',{name:'Керування користувачами',exact:true}).click();await page.waitForURL('**/admin/users');
  assert.match(await page.locator('body').innerText(),/окремого активного персонального Admin ще немає/);
  const admin=await create('account-admin','admin');
  await page.goto(base+'/admin/users');assert.doesNotMatch(await page.locator('body').innerText(),/окремого активного персонального Admin ще немає/);
  assert.match(await page.locator(`[data-account-id="${master}"]`).innerText(),/Master/);
  console.log('PASS accounts: Master transition warning, GUI creation of the first Admin and distinct Master label');

  const editor=await create('account-editor','editor');
  let form=page.locator(`form[action="/admin/users/${editor}"]`);
  await form.locator('[name=display_name]').fill('Збережене виправлення');await submit(form);
  form=page.locator(`form[action="/admin/users/${editor}"]`);
  await form.locator('[name=role]').selectOption('viewer');await form.locator('[name=confirmed]').check();await submit(form);
  await page.getByRole('link',{name:'Історія змін',exact:true}).click();await page.waitForURL('**/admin/users/audit?*');
  assert.match(await page.locator('body').innerText(),/Збережене виправлення/);assert.match(await page.locator('body').innerText(),/Зміна ролі/);
  console.log('PASS accounts: display-name editing, confirmed role change and readable before/after audit');

  await page.goto(base+'/admin/users/new');form=page.locator('[data-account-form]');await form.locator('[name=username]').fill('account-editor');await form.locator('[name=display_name]').fill('Залишити чернетку');await form.locator('[name=password]').fill(password);await form.locator('[name=confirm_password]').fill(password);await form.locator('button').click();
  await form.locator('[data-account-error]:visible').waitFor();assert.equal(await form.locator('[name=username]').inputValue(),'account-editor');assert.equal(await form.locator('[name=display_name]').inputValue(),'Залишити чернетку');assert.equal(await form.locator('[name=password]').inputValue(),'');
  console.log('PASS accounts: duplicate username errors retain non-secret drafts and clear password fields');

  await signIn('account-admin',password);await page.goto(base+`/admin/users/${master}`);
  assert.equal(await page.locator('[data-account-form]').count(),0);
  assert.equal((await context.request.post(base+`/admin/users/${master}/revoke-sessions`,{data:{revision:1,confirmed:true}})).status(),403);
  const target=await(await context.request.get(base+`/admin/users/${editor}`,{headers:{Accept:'application/json'}})).json();
  const denied=await context.request.post(base+`/admin/users/${editor}`,{data:{revision:target.account.revision,role:'master',confirmed:true}});assert.equal(denied.status(),409);
  console.log('PASS accounts: Admin cannot edit Master or create another Master through API');

  // A second live browser session is revoked on disable, and stays revoked on enable.
  const other=await context.browser().newContext();
  try{
   assert.equal((await other.request.post(base+'/auth/login',{data:{username:'account-editor',password}})).status(),200);
   await page.goto(base+`/admin/users/${editor}`);
   await page.getByText('Вимкнути користувача',{exact:true}).click();form=page.locator('form[action$="/state"]');await form.locator('[name=confirmed]').check();await submit(form);
   assert.equal((await other.request.get(base+'/auth/me')).status(),401);assert.match(await page.locator('body').innerText(),/Вимкнений адміністратором/);
   await page.getByText('Увімкнути користувача',{exact:true}).click();form=page.locator('form[action$="/state"]');await form.locator('[name=confirmed]').check();await submit(form);
   assert.equal((await other.request.get(base+'/auth/me')).status(),401);
  }finally{await other.close();}
  console.log('PASS accounts: disable revokes real sessions, enable never restores revoked cookies');

  await page.goto(base+`/admin/users/${admin}`);await page.getByText('Вимкнути користувача',{exact:true}).click();form=page.locator('form[action$="/state"]');await form.locator('[name=confirmed]').check();await form.locator('button').click();await form.locator('[data-account-error]:visible').waitFor();assert.match(await form.locator('[data-account-error]').innerText(),/останнього/);
  assert.equal(await form.locator('[name=confirmed]').isChecked(),true);
  console.log('PASS accounts: last active Admin cannot be disabled and the form remains open');

  await page.goto(base+`/admin/users/${editor}`);await page.getByText('Адміністративне скидання пароля',{exact:true}).click();form=page.locator('form[action$="/reset-password"]');await form.locator('[name=password]').fill(password+'-reset');await form.locator('[name=confirm_password]').fill(password+'-reset');await form.locator('[name=confirmed]').check();await submit(form);
  await signIn('account-editor',password+'-reset');await page.goto(base+'/account/password');form=page.locator('[data-account-form]');await form.locator('[name=current_password]').fill(password+'-reset');await form.locator('[name=password]').fill(password+'-own');await form.locator('[name=confirm_password]').fill(password+'-own');await submit(form);assert.equal(new URL(page.url()).pathname,'/auth/login');assert.equal((await context.request.get(base+'/auth/me')).status(),401);
  await signIn('account-editor',password+'-own');assert.equal((await context.request.get(base+'/admin/users')).status(),403);
  console.log('PASS accounts: Admin password reset and Viewer own-password change revoke sessions and preserve role');

  await signIn('browser-admin',adminToken);await page.goto(base+`/admin/users/${master}`);assert.equal(await page.locator('[name=role]').count(),0);assert.equal(await page.locator('form[action$="/reset-password"]').count(),0);assert.equal(await page.locator('form[action$="/state"]').count(),0);
  await page.setViewportSize({width:390,height:844});await page.goto(base+'/admin/users');assert.equal(await page.locator('table').count(),1);assert.equal(await page.locator('[data-account-id]').count(),3);
  assert.deepEqual(errors,[]);console.log('PASS accounts: Master protections remain in its own GUI; user list is usable on a narrow viewport');
 }finally{await page.close();}
};

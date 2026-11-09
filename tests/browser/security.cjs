const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await context.clearCookies();
  for(const path of ['/persons','/events/data','/staff/history','/admin','/openapi.json','/persons/1/documents/files/1'])assert.equal((await context.request.get(base+path)).status(),401,path);
  await page.goto(base+'/staff/history?version_id=1&q=30');assert.equal(new URL(page.url()).pathname,'/auth/login');assert.doesNotMatch(await page.locator('body').innerText(),/Альфа|Бета/);
  await page.locator('[name=username]').fill('browser-admin');await page.locator('[name=password]').fill(adminToken);await Promise.all([page.waitForURL('**/staff/history?version_id=1&q=30'),page.getByRole('button',{name:'Увійти',exact:true}).click()]);
  assert.equal(await page.locator('[data-position-id]').count(),1);console.log('PASS security: anonymous pages redirect without data, APIs/files return 401, personal login restores safe original URL');
  const me=await(await context.request.get(base+'/auth/me')).json();assert.equal(me.username,'browser-admin');
  const bad=await page.evaluate(async()=>{const r=await fetch('/staff/structures',{method:'POST',body:new URLSearchParams({code:'bad',name:'bad'}),headers:{'X-CSRF-Token':'wrong'}});return r.status;});assert.equal(bad,403);
  // Real legacy fetch has no local CSRF implementation; the shared wrapper supplies it.
  const created=await page.evaluate(async()=>{const r=await fetch('/staff/structures',{method:'POST',body:new URLSearchParams({code:'security-browser',name:'Тестова структура'})});return r.status;});assert.equal(created,200);
  const oldToken=await page.locator('meta[name="project2-csrf"]').getAttribute('content');
  await page.evaluate(async password=>fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'browser-admin',password})}),adminToken);
  const pending=await require('./mfa_helpers.cjs').verify(context.request,base);
  const renewed=await page.evaluate(async({csrf,oldToken})=>{const r=await fetch('/auth/mfa/finish',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:'{}'});const data=await r.json();return {changed:oldToken!==data.csrf_token,meta:document.querySelector('meta[name="project2-csrf"]').content===data.csrf_token,forms:[...document.querySelectorAll('form input[name=csrf]')].every(n=>n.value===data.csrf_token)};},{csrf:pending.csrf_token,oldToken});assert.deepEqual(renewed,{changed:true,meta:true,forms:true});
  console.log('PASS security: existing fetch callers gain valid CSRF, explicit wrong tokens fail and re-login refreshes native forms');
  await context.request.post(base+'/auth/users',{data:{username:'browser-viewer',display_name:'Тестовий спостерігач',role:'user',password:adminToken}});
  await context.request.post(base+'/auth/logout');
  const expired=await page.evaluate(async()=>{const response=await fetch('/events/data');return response.status;});assert.equal(expired,401);await page.locator('#session-expired').waitFor();
  await page.goto(base+'/auth/login?return_to='+encodeURIComponent('//evil.example'));await page.locator('[name=username]').fill('browser-viewer');await page.locator('[name=password]').fill(adminToken);await Promise.all([page.waitForURL('**/persons'),page.getByRole('button',{name:'Увійти',exact:true}).click()]);
  assert.equal((await context.request.get(base+'/admin')).status(),403);assert.equal((await context.request.post(base+'/staff/structures',{form:{code:'denied',name:'denied'}})).status(),403);
  console.log('PASS security: session expiry is visible; unsafe return is rejected and viewer cannot administer or write');
  await page.getByRole('button',{name:'Меню користувача та тема оформлення'}).click();await page.locator('[data-personal-logout] button').click();await page.waitForURL('**/auth/login');assert.equal((await context.request.get(base+'/persons')).status(),401);
  console.log('PASS security: logout revokes the personal session and denies protected reads');
  const native=await context.browser().newContext({javaScriptEnabled:false});
  try{
   const login=await native.request.post(base+'/auth/login',{data:{username:'browser-admin',password:adminToken}});assert.equal(login.status(),200);await require('./mfa_helpers.cjs').complete(native.request,base);
   const formPage=await native.newPage();await formPage.goto(base+'/admin/staff');const form=formPage.locator('form[action="/staff/structures"]');
   await form.locator('..').locator(':scope > summary').click();await form.locator('[name=code]').fill('security-no-js');await form.locator('[name=name]').fill('Нативна тестова форма');
   assert.ok(await form.locator('[name=csrf]').first().inputValue());await Promise.all([formPage.waitForNavigation(),form.locator('button').click()]);assert.match(await formPage.locator('body').innerText(),/Структуру створено/);
  }finally{await native.close();}
  assert.deepEqual(errors,[]);console.log('PASS security: native HTML POST carries server CSRF and works with JavaScript disabled');
 }finally{await page.close();}
};

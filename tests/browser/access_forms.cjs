/* Actual Passkey login/reauth; the main page retains live drafts without persistence or replay. */
const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken,assets})=>{
 const setup=await context.request.post(base+'/_column-test/access/setup');assert.equal(setup.status(),200);const ids=await setup.json();
 const make=async parent=>(await(await context.request.post(base+'/admin/organization/units',{data:{kind:'platoon',name:'3 взвод',parent_id:parent,formed_on:'1990-01-01'}})).json()).unit_id;
 const a=await make(ids.unit),b=await make(ids.hidden);
 const own=await context.browser().newContext({locale:'en-US',timezoneId:'Europe/Kyiv'}),page=await own.newPage(),errors=[],writes=[];
 own.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));page.on('pageerror',e=>errors.push(e.message));
 await own.route('https://cdn.jsdelivr.net/npm/bootstrap@*/dist/**',route=>{const url=route.request().url(),file=url.split('/dist/')[1],version=url.split('bootstrap@')[1].split('/')[0];return route.fulfill({body:assets[`${version}/${file}`],contentType:file.endsWith('.js')?'application/javascript':'text/css'});});
 await own.addCookies(await context.cookies());
 const cdp=await own.newCDPSession(page);await cdp.send('WebAuthn.enable');await cdp.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
 try{
  const me=await(await own.request.get(base+'/auth/me')).json();assert.equal((await own.request.post(base+'/account/security/add-factor',{headers:{'X-CSRF-Token':me.csrf_token},data:{}})).status(),200);
  await page.goto(base+'/auth/mfa');await page.locator('[data-passkey-register]:visible').waitFor();await page.locator('[data-passkey-register]').click();await page.locator('[data-finish]:visible').waitFor();await Promise.all([page.waitForURL('**/account/security'),page.locator('[data-finish]').click()]);
  await own.clearCookies();await page.goto(base+'/auth/login');await page.locator('[name=username]').fill('browser-admin');await page.locator('[name=password]').fill(adminToken);await Promise.all([page.waitForURL('**/auth/mfa'),page.locator('[type=submit]').click()]);
  await page.locator('[data-passkey-auth]:visible').waitFor();await page.locator('[data-passkey-auth]').click();await page.locator('[data-finish]:visible').waitFor();await Promise.all([page.waitForURL('**/persons'),page.locator('[data-finish]').click()]);
  await page.goto(base+'/admin/access?user_id='+ids.user);await page.locator('[data-access-matrix] tbody tr').first().waitFor();
  const editor=page.locator('[data-template-editor]');await editor.locator('..').locator(':scope > summary').click();await editor.locator('[name=name]').fill('Читання взводу');await editor.locator('[name=reason]').fill('Перевірка свіжого Passkey');await editor.locator('button:not([type=button])').click();
  await page.getByText(/Шаблон збережено · ID/).waitFor();assert.equal(await page.locator('[data-access-reauth].show').count(),0);
  console.log('PASS access forms: actual CTAP2 Passkey login permits fresh ACL changes without another challenge');
  const assign=page.locator('[data-template-assign]');await assign.locator('[data-access-choice-search=template]').fill('ЧИТАННЯ');await assign.locator('[name=template_id]').selectOption({label:'Читання взводу'});const template=Number(await assign.locator('[name=template_id]').inputValue());assert.ok(template);
  await assign.locator('[data-access-choice-search=unit]').fill('3 ВЗВОД');assert.equal(await assign.locator('[name=unit_id] option').count(),3);
  const label=await assign.locator(`[name=unit_id] option[value="${a}"]`).innerText();assert.equal(label,'ACL батальйон / ACL доступна рота / 3 взвод');assert.notEqual(label,await assign.locator(`[name=unit_id] option[value="${b}"]`).innerText());await assign.locator('[name=unit_id]').selectOption(String(a));
  for(const selector of ['[data-access-rule]','[data-template-assign]','[data-temporary-access]','[data-access-delegate]']){
   const form=page.locator(selector),section=form.locator('..');if(await section.evaluate(n=>n.tagName==='DETAILS'&&!n.open))await section.locator(':scope > summary').click();await form.locator('[data-datetime-date-for=starts_at]').fill('12.11.2030');await form.locator('[data-datetime-time-for=starts_at]').fill('09:05');await form.locator('[data-datetime-date-for=ends_at]').fill('13.11.2030');await form.locator('[data-datetime-time-for=ends_at]').fill('18:30');assert.equal(await form.locator('[name=starts_at]').inputValue(),'2030-11-12T09:05');
  }
  await assign.locator('[name=reason]').fill('Явне призначення за повним шляхом');
  await assign.locator('[data-datetime-date-for=ends_at]').fill('31.02.2030');assert.equal(await assign.evaluate(n=>n.checkValidity()),false);await assign.locator('[data-datetime-date-for=ends_at]').fill('13.11.2030');
  await assign.locator('[data-datetime-date-for=starts_at]').fill('');await assign.locator('[data-datetime-time-for=starts_at]').fill('');assert.equal(await assign.locator('[name=starts_at]').inputValue(),'');assert.equal(await assign.evaluate(n=>n.checkValidity()),true);await assign.locator('[data-datetime-date-for=starts_at]').fill('12.11.2030');await assign.locator('[data-datetime-time-for=starts_at]').fill('09:05');
  const [sent]=await Promise.all([page.waitForRequest(r=>r.method()==='POST'&&r.url().endsWith(`/users/${ids.user}/template`)),assign.locator('button:not([type=button])').click()]);const body=sent.postDataJSON();assert.equal(body.template_id,template);assert.equal(body.unit_id,a);assert.equal(body.starts_at,'2030-11-12T07:05:00.000Z');assert.equal(body.ends_at,'2030-11-13T16:30:00.000Z');await page.getByText('Шаблон призначено.',{exact:true}).waitFor();
  console.log('PASS access forms: names and full paths distinguish duplicate units; unchanged IDs and UTC timestamps reach the server');
  await page.locator('[data-access-expand]').click();const choice=page.locator(`[data-access-row="unit:${ids.unit}"] [data-rule-category=basic][data-rule-action=read]`);await choice.selectOption('ALLOW');const matrix=page.locator('[data-access-save]');await matrix.locator('[name=reason]').fill('Чернетка, яку потрібно зберегти');const draft=await assign.evaluate(n=>[...new FormData(n)]);
  page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('/admin/access/'))writes.push(r.url());});
  assert.equal((await context.request.post(base+'/_column-test/access/expire-mfa')).status(),200);
  await matrix.locator('button').click();const modal=page.locator('[data-access-reauth]');await modal.locator('iframe').waitFor({state:'visible'});assert.doesNotMatch(await modal.innerText(),/MFA_REAUTH_REQUIRED/);assert.equal(writes.length,1);
  await page.evaluate(()=>postMessage({type:'project2:mfa-confirmed'},location.origin));assert.equal(await modal.evaluate(n=>n.classList.contains('show')),true);
  await modal.locator('[data-bs-dismiss=modal]').last().click();await modal.waitFor({state:'hidden'});assert.deepEqual(await assign.evaluate(n=>[...new FormData(n)]),draft);
  await matrix.locator('button').click();await modal.waitFor({state:'visible'});const frame=page.frameLocator('[data-access-reauth-frame]');await frame.locator('[data-reauth] [name=password]').fill(adminToken);await frame.locator('[data-reauth] button').click();await frame.locator('[data-passkey-auth]:visible').waitFor();await frame.locator('[data-passkey-auth]').click();await frame.locator('[data-finish]:visible').waitFor();await frame.locator('[data-finish]').click();await modal.waitFor({state:'hidden'});
  assert.equal(writes.length,2);assert.equal(await choice.inputValue(),'ALLOW');assert.equal(await matrix.locator('[name=reason]').inputValue(),'Чернетка, яку потрібно зберегти');assert.deepEqual(await assign.evaluate(n=>[...new FormData(n)]),draft);
  await page.getByText(/Особу підтверджено. Чернетка збережена/).waitFor();await matrix.locator('button').click();await page.getByText('Матрицю збережено. Права перераховані на сервері.',{exact:true}).waitFor();assert.equal(writes.length,3);
  console.log('PASS access forms: expired MFA offers existing password/Passkey flow; cancellation and completion retain drafts, reject foreign messages and never replay writes');
  for(const width of [390,768,1280]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  assert.deepEqual(errors,[]);console.log('PASS access forms: English-locale browser shows Ukrainian dates and 24-hour times with no page overflow or JavaScript errors');
 }finally{await own.close();}
};

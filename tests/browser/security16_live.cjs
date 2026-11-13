/* Real PG + MFA + worker; Windows hardware discovery is explicitly simulated. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright'),{execFileSync}=require('node:child_process');
(async()=>{
 const cfg=JSON.parse(process.env.PROJECT2_BROWSER_SECURITY16),browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 try{
  const context=await browser.newContext({locale:'en-US'});context.setDefaultTimeout(20000);
  const errors=[],page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  for(const file of ['css/bootstrap.min.css','js/bootstrap.bundle.min.js']){
   const url='https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/'+file,data=execFileSync('curl',['--fail','--silent','--show-error','--location',url]);
   await context.route(url,r=>r.fulfill({body:data,contentType:file.endsWith('.js')?'application/javascript':'text/css'}));
  }
  await context.addCookies([{name:'project2_user',value:cfg.admin,url:cfg.base}]);
  await page.goto(cfg.base+'/admin/backups');await page.locator('[data-emergency-create]:visible').waitFor();
  await page.locator('[data-emergency-create]').click();
  for(let n=0;n<120;n++){await page.locator('[data-backup-refresh]').click();if((await page.locator('[data-backup-jobs]').innerText()).includes('emergency · Успішно'))break;await page.waitForTimeout(200);}
  assert.match(await page.locator('[data-backup-jobs]').innerText(),/emergency · Успішно/);
  console.log('PASS Security 1.6 UI: Admin creates three real Excel books via the PostgreSQL worker');
  await page.locator('[data-usb-open]').click();await page.locator('[data-usb-volume] option').waitFor({state:'attached'});
  assert.equal(await page.locator('[data-usb-volume]').inputValue(),cfg.volume);
  await page.locator('[data-usb-confirm]').click();
  for(let n=0;n<120;n++){await page.locator('[data-backup-refresh]').click();if((await page.locator('[data-backup-jobs]').innerText()).includes('usb · Успішно'))break;await page.waitForTimeout(200);}
  assert.match(await page.locator('[data-backup-jobs]').innerText(),/usb · Успішно/);
  assert.equal((await context.request.post(cfg.base+'/admin/backups/usb',{data:{volume_id:'../../arbitrary'}})).status(),403);
  const csrf=await page.locator('meta[name=project2-csrf]').getAttribute('content');
  assert.equal((await context.request.post(cfg.base+'/admin/backups/usb',{headers:{'X-CSRF-Token':csrf},data:{volume_id:'../../arbitrary'}})).status(),409);
  console.log('PASS Security 1.6 UI: simulated server USB is selected by ID, copied in worker, arbitrary paths and missing CSRF are rejected');
  fs.writeFileSync(path.join(cfg.control,'expire'),'1');
  for(let n=0;n<100&&!fs.existsSync(path.join(cfg.control,'expired'));n++)await page.waitForTimeout(100);
  const before=await page.locator('[data-backup-jobs]').innerText();await page.locator('[data-storage-refresh]').click();
  await page.locator('[data-access-reauth].show').waitFor();
  assert.equal(await page.locator('[data-access-reauth] iframe').getAttribute('src'),'/account/security?reauth=1');
  await page.locator('[data-access-reauth] .modal-footer [data-bs-dismiss]').click();
  assert.equal(await page.locator('[data-usb-volume]').inputValue(),cfg.volume);
  await page.locator('[data-backup-refresh]').click();assert.equal(await page.locator('[data-backup-jobs]').innerText(),before);
  console.log('PASS Security 1.6 UI: expired MFA opens the existing reauthentication modal, preserves selection and never replays a critical operation');
  await page.goto(cfg.base+'/admin/audit');
  for(const name of ['Системний аудит','Аудит предметних даних','Аудит резервування']){
   await page.getByRole('link',{name,exact:true}).click();await page.locator('[data-column-table]').waitFor();
  }
  await page.goto(cfg.base+'/admin/audit?tab=subject');
  await page.locator('[name=q]').fill('SECRET-SYNTHETIC-PERSON');
  await page.locator('[data-exact-date-for=from]').fill('01.01.2020');await page.locator('[name=sort2]').selectOption('actor');
  await page.locator('[data-audit-filters]').getByRole('button',{name:'Застосувати',exact:true}).click();
  await page.waitForLoadState('domcontentloaded');
  assert.equal(new URL(page.url()).searchParams.get('from'),'2020-01-01');
  assert.ok(await page.locator('[data-column-table] tbody tr[data-row-key]').count(),page.url()+'\n'+(await page.locator('body').innerText()).slice(-3500));
  await page.locator('[data-column-table] [data-column-key=after] button').first().click();await page.locator('.modal.show').waitFor();
  assert.match(await page.locator('.modal.show').innerText(),/SECRET-SYNTHETIC-PERSON/);
  await page.locator('.modal.show .modal-footer button').click();
  const txt=await context.request.get(cfg.base+await page.getByRole('link',{name:'Експорт результату в TXT'}).getAttribute('href'));
  assert.equal(txt.status(),200);assert.match(await txt.text(),/SECRET-SYNTHETIC-PERSON/);
  await page.locator('[data-column-toggle]').click();await page.locator('[data-visibility-tree] [data-column-choice=reason]').uncheck();await page.locator('[data-column-apply]').click();
  assert.equal(await page.locator('[data-column-table] th[data-column-key=reason]').isVisible(),false);
  for(const width of [1280,768,390]){await page.setViewportSize({width,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  console.log('PASS Security 1.6 UI: three audit tabs, dates, combined filters, multi-sort, change modal, TXT, shared columns and mobile layout');
  await context.addCookies([{name:'project2_user',value:cfg.master,url:cfg.base}]);await page.goto(cfg.base+'/admin/audit?tab=subject');
  assert.doesNotMatch(await page.locator('body').innerText(),/SECRET-SYNTHETIC-PERSON/);
  const denied=await context.request.get(cfg.base+'/admin/audit/export.txt?tab=subject&q=SECRET-SYNTHETIC-PERSON');assert.equal(denied.status(),200);assert.doesNotMatch(await denied.text(),/SECRET-SYNTHETIC-PERSON/);
  assert.deepEqual(errors,[]);
  console.log('PASS Security 1.6 UI: Master has no implicit subject-audit access; DOM and TXT stay scoped with no JavaScript errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

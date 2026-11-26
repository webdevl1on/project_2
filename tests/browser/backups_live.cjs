/* Real PostgreSQL backend + durable worker; fixture session has completed actual MFA. */
const assert=require('node:assert/strict');const {chromium}=require('playwright');const {execFileSync}=require('node:child_process');
(async()=>{const settings=JSON.parse(process.env.PROJECT2_BROWSER_BACKUP),browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
try{const context=await browser.newContext(),errors=[];const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
for(const version of ['5.3.3','5.3.8'])for(const file of ['css/bootstrap.min.css','js/bootstrap.bundle.min.js']){const data=execFileSync('curl',['--fail','--silent','--show-error','--location',`https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`]);await context.route(`https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`,r=>r.fulfill({body:data,contentType:file.endsWith('.js')?'application/javascript':'text/css'}));}
await context.addCookies([{name:'project2_user',value:settings.token,url:settings.base}]);await page.goto(settings.base+'/admin/backups');await page.locator('[data-backup-create]:visible').waitFor();
await page.locator('[data-backup-create]').click();await page.locator('[data-backup-message]').getByText(/прийнято worker/).waitFor();
await page.locator('[data-backup-current]').getByText(/У черзі/).waitFor();
assert.equal(await page.locator('[data-backup-create]').isDisabled(),true);
await page.locator('[data-backup-list]').getByText('Цілісність підтверджено',{exact:true}).waitFor();
assert.equal(await page.locator('[data-backup-list] tr').count(),1);
await page.locator('[data-backup-current] article').filter({hasText:'Створення резервної копії'}).getByText('Готово',{exact:true}).waitFor();
console.log('PASS backup UI: real Master queues a job, sees progress and receives the completed snapshot through polling');
await page.getByRole('button',{name:'Перевірити',exact:true}).click();
await page.locator('[data-backup-jobs] article').filter({hasText:'Перевірка резервної копії'}).getByText('Готово',{exact:true}).waitFor();
assert.doesNotMatch(await page.locator('body').innerText(),/PROJECT2_MFA_KEYS|secret-key|main-key/);
assert.equal(await page.getByRole('button',{name:/Відновити/}).count(),0);console.log('PASS backup UI: manual verification runs in the worker; archives, secrets and restore actions are not exposed');
await page.locator('[data-backup-guide] summary').click();
await page.reload();
await page.locator('[data-backup-create]:visible').waitFor();
assert.equal(await page.locator('[data-backup-guide]').evaluate(el=>el.open),false);
await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);console.log('PASS backup UI: narrow viewport remains usable and no JavaScript errors occur');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

/* Real PostgreSQL backend + durable worker; fixture session has completed actual MFA. */
const assert=require('node:assert/strict');const {chromium}=require('playwright');const {execFileSync}=require('node:child_process');
(async()=>{const settings=JSON.parse(process.env.PROJECT2_BROWSER_BACKUP),browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
try{const context=await browser.newContext(),errors=[];const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
for(const version of ['5.3.3','5.3.8'])for(const file of ['css/bootstrap.min.css','js/bootstrap.bundle.min.js']){const data=execFileSync('curl',['--fail','--silent','--show-error','--location',`https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`]);await context.route(`https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`,r=>r.fulfill({body:data,contentType:file.endsWith('.js')?'application/javascript':'text/css'}));}
await context.addCookies([{name:'project2_user',value:settings.token,url:settings.base}]);await page.goto(settings.base+'/admin/backups');await page.locator('[data-backup-create]:visible').waitFor();
await page.locator('[data-backup-create]').click();await page.locator('[data-backup-message]').getByText(/прийнято worker/).waitFor();
for(let n=0;n<90;n++){await page.locator('[data-backup-refresh]').click();if(await page.locator('[data-backup-list] tr').count())break;await page.waitForTimeout(250);}
await page.locator('[data-backup-list]').getByText('VERIFIED',{exact:true}).waitFor();assert.equal(await page.locator('[data-backup-list] tr').count(),1);
console.log('PASS backup UI: real Master creates a durable job and sees a verified PostgreSQL/files backup after worker completion');
await page.getByRole('button',{name:'Перевірити',exact:true}).click();
for(let n=0;n<90;n++){await page.locator('[data-backup-refresh]').click();if((await page.locator('[data-backup-jobs]').innerText()).includes('verify · SUCCESS'))break;await page.waitForTimeout(250);}
assert.match(await page.locator('[data-backup-jobs]').innerText(),/verify · SUCCESS/);assert.doesNotMatch(await page.locator('body').innerText(),/PROJECT2_MFA_KEYS|secret-key|main-key/);
assert.equal(await page.getByRole('button',{name:/Відновити/}).count(),0);console.log('PASS backup UI: manual verification runs in the worker; archives, secrets and restore actions are not exposed');
await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);console.log('PASS backup UI: narrow viewport remains usable and no JavaScript errors occur');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

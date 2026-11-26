/* Real PostgreSQL backend + durable worker; fixture session has completed actual MFA. */
const assert=require('node:assert/strict');const {chromium}=require('playwright');const {execFileSync}=require('node:child_process');
(async()=>{const settings=JSON.parse(process.env.PROJECT2_BROWSER_BACKUP),browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
try{const context=await browser.newContext(),errors=[];const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
for(const version of ['5.3.3','5.3.8'])for(const file of ['css/bootstrap.min.css','js/bootstrap.bundle.min.js']){const data=execFileSync('curl',['--fail','--silent','--show-error','--location',`https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`]);await context.route(`https://cdn.jsdelivr.net/npm/bootstrap@${version}/dist/${file}`,r=>r.fulfill({body:data,contentType:file.endsWith('.js')?'application/javascript':'text/css'}));}
await context.addCookies([{name:'project2_user',value:settings.token,url:settings.base}]);await page.goto(settings.base+'/admin/backups');await page.locator('[data-backup-create]:visible').waitFor();
const tab = name => page.getByRole('tab', {name, exact:true});
const catalog = page.getByRole('region', {name:'Таблиця резервних копій'});
assert.equal(await tab('Огляд').getAttribute('aria-selected'), 'true');
assert.equal(await catalog.isVisible(), false);
assert.equal(await page.locator('[data-backup-jobs]').isVisible(), false);
assert.equal(await page.locator('[data-backup-events]').isVisible(), false);
await page.locator('[data-backup-create]').click();await page.locator('[data-backup-message]').getByText(/прийнято worker/).waitFor();
await page.locator('[data-backup-current]').getByText(/У черзі/).waitFor();
assert.equal(await page.locator('[data-backup-create]').isDisabled(),true);
await tab('Резервні копії').click();
await page.locator('[data-backup-list]').getByText('Цілісність підтверджено',{exact:true}).waitFor();
assert.equal(await page.locator('[data-backup-list] tr').count(),1);
await tab('Огляд').click();
await page.locator('[data-backup-current] article').filter({hasText:'Створення резервної копії'}).getByText('Готово',{exact:true}).waitFor();
console.log('PASS backup UI: real Master queues a job, sees progress and receives the completed snapshot through polling');
await tab('Резервні копії').click();
await page.getByRole('button',{name:'Перевірити',exact:true}).click();
await tab('Останні завдання').click();
await page.locator('[data-backup-jobs] article').filter({hasText:'Перевірка резервної копії'}).getByText('Готово',{exact:true}).waitFor();
assert.doesNotMatch(await page.locator('body').innerText(),/PROJECT2_MFA_KEYS|secret-key|main-key/);
assert.equal(await page.getByRole('button',{name:/Відновити/}).count(),0);console.log('PASS backup UI: manual verification runs in the worker; archives, secrets and restore actions are not exposed');
await tab('Огляд').click();
await page.locator('[data-backup-guide] summary').click();
await tab('Журнал операцій').click();
await page.reload();
await page.locator('[data-backup-create]:visible').waitFor();
assert.equal(await page.locator('[data-backup-guide]').evaluate(el=>el.open),false);
assert.equal(await tab('Огляд').getAttribute('aria-selected'), 'true');
await page.setViewportSize({width:390,height:844});
for (const name of ['Огляд', 'Резервні копії', 'Останні завдання', 'Журнал операцій']) {
  await tab(name).click();
  assert.equal(await tab(name).getAttribute('aria-selected'), 'true');
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), name);
}
assert.equal(await page.getByRole('link',{name:'Фільтри, сортування та TXT-експорт журналу'}).isVisible(),true);
await tab('Резервні копії').click();
assert.ok(await catalog.evaluate(region => {
  const body = region.querySelector('tbody');
  const row = body.rows[0];
  for (let index = 0; index < 30; index++) body.append(row.cloneNode(true));
  return region.scrollHeight > region.clientHeight && document.documentElement.scrollWidth <= innerWidth + 1;
}));
assert.deepEqual(errors,[]);console.log('PASS backup UI: tabs and catalog scrolling work on a narrow viewport');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});

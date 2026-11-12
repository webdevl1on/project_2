/* Manual-review regressions, real forms/MFA/CSRF, isolated synthetic fixture. */
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const date=(form,name)=>form.locator(`[data-exact-date-for="${name}"]`);
 const open=async form=>{const details=form.locator('..');if(!await details.evaluate(n=>n.open))await details.locator(':scope > summary').click();};
 const save=async form=>Promise.all([page.waitForNavigation(),form.locator('button:not([type=button])').click()]);
 try{
  await page.goto(base+'/admin/staff');
  assert.doesNotMatch(await page.locator('[data-staff-selection] [name=version_id]').innerText(),/main \(main\)|\d{4}-\d{2}-\d{2}/);
  const correction=page.locator('[data-staff-version-correction]');await open(correction);
  const original=await correction.locator('[name=valid_from]').inputValue();
  assert.equal(await date(correction,'valid_from').inputValue(),original.split('-').reverse().join('.'));
  await date(correction,'valid_from').fill('01.01.2090');await correction.locator('[name=name]').fill('Збережена чернетка');
  await correction.locator('[data-staff-period-warning]:visible').waitFor();const before=await correction.evaluate(n=>[...new FormData(n)]);
  await correction.locator('button:not([type=button])').click();await correction.locator('[data-history-form-error]').filter({hasText:'Неможливо змінити період штатки'}).waitFor();
  assert.deepEqual(await correction.evaluate(n=>[...new FormData(n)]),before);
  await date(correction,'valid_from').fill(original.split('-').reverse().join('.'));await correction.locator('[data-staff-period-warning]').waitFor({state:'hidden'});
  await correction.locator('[name=name]').fill('Уточнена тестова штатка');await save(correction);
  assert.match(await page.locator('[data-staff-selection] [name=version_id]').innerText(),/Уточнена тестова штатка/);
  console.log('PASS staff review: Ukrainian labels/dates, ISO values, dependent-assignment preview, precise refusal and retained drafts');
  const position=page.locator('[data-staff-positions] form').first();await open(position);await position.locator('[name=name_short]').fill('Уточнена посада');await save(position);
  assert.equal(await page.locator('[data-staff-positions] form').first().locator('[name=name_short]').inputValue(),'уточнена посада');
  fs.mkdirSync('/tmp/project2-review-screenshots',{recursive:true});
  for(const theme of ['light','dark','military'])for(const width of [390,768,1280,1920]){
   await page.setViewportSize({width,height:900});await page.evaluate(mode=>ProjectTheme.set(mode,document),theme);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),theme+'/'+width);
   const sections=page.locator('[data-staff-management] > section'),a=await sections.first().boundingBox(),b=await sections.nth(1).boundingBox();
   if(width>=1280)assert.ok(Math.abs(a.y-b.y)<2&&b.x>a.x);else if(width===390)assert.ok(b.y>a.y);
   if(width===1280)await page.screenshot({path:`/tmp/project2-review-screenshots/staff-${theme}.png`});
  }
  console.log('PASS staff review: position editing and two/one-column layout in all themes at 390/768/1280/1920');
  await page.setViewportSize({width:1280,height:900});
  const create=page.locator('form[action="/staff/structures"]');await open(create);await create.locator('[name=code]').fill('review');await create.locator('[name=name]').fill('Окрема тестова структура');await save(create);
  assert.equal(await page.locator('[data-staff-positions]').count(),0);
  await page.getByRole('button',{name:'Завантажити штатну структуру',exact:true}).click();const modal=page.locator('#staff-import-modal');
  await modal.locator('[name=file]').setInputFiles(path.resolve(__dirname,'../../reference_data.xlsx'));await modal.locator('[name=name]').fill('Тестовий штат');await date(modal,'valid_from').fill('01.01.1999');await date(modal,'valid_to').fill('31.12.1999');
  await Promise.all([page.waitForNavigation(),modal.getByRole('button',{name:'Перевірити файл'}).click()]);
  await Promise.all([page.waitForNavigation(),page.getByRole('button',{name:'Підтвердити завантаження'}).click()]);
  assert.match(await page.locator('[data-staff-selection] [name=version_id]').innerText(),/Тестовий штат · 01.01.1999 — 31.12.1999/);
  const close=page.locator('form[action$="/close"]');await open(close);await date(close,'valid_to').fill('30.06.1999');await close.locator('[name=confirmed]').check();await save(close);
  assert.match(await page.locator('.alert[role=status]').innerText(),/Версію та всі її відкриті призначення завершено/);
  assert.deepEqual(errors,[]);console.log('PASS staff review: independent structure, Excel preview/confirmation and explicit version closure retain existing routes');
 }finally{await page.close();}
};

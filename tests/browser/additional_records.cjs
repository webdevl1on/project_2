const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await context.request.get(base+'/auth/me');await page.goto(base+'/person_full_info/3#education');
  const panel=page.locator('[data-additional-panel=education]'),form=panel.locator('form'),editor=panel.locator('[data-additional-editor]');
  await panel.locator('[data-additional-content]').waitFor({state:'visible'});assert.equal(await editor.isVisible(),false);
  await panel.locator('[data-additional-new]').click();await form.locator('[name=level_code]').selectOption('higher_bachelor');
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'});assert.equal(await panel.locator('[data-additional-record]').count(),1);
  await panel.locator('[data-additional-record]').evaluate(n=>n.open=true);await panel.getByRole('button',{name:'Редагувати',exact:true}).click();
  await form.locator('[name=institution]').fill('Тестовий заклад');await form.locator('[data-exact-date-for=started_on]').fill('31.10.2026');await form.locator('[data-exact-date-for=ended_on]').fill('30.10.2026');
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();await panel.locator('[data-additional-message]').filter({hasText:'Дата закінчення'}).waitFor();
  assert.equal(await form.locator('[name=institution]').inputValue(),'Тестовий заклад');assert.equal(await form.locator('[data-exact-date-for=ended_on]').inputValue(),'30.10.2026');
  await form.locator('[data-exact-date-for=ended_on]').fill('');await form.getByRole('button',{name:'Зберегти',exact:true}).click();await editor.waitFor({state:'hidden'});
  assert.equal(await panel.locator('[data-additional-record]').count(),1);assert.match(await panel.locator('[data-additional-record]').innerText(),/31.10.2026/);assert.equal(new URL(page.url()).hash,'#education');
  await panel.locator('[data-additional-new]').click();assert.equal(await form.locator('[name=institution]').inputValue(),'');assert.equal(await form.getAttribute('data-key'),'');await panel.locator('[data-additional-cancel]').click();
  await page.reload();await panel.locator('[data-additional-record]').filter({hasText:'Тестовий заклад'}).waitFor();assert.deepEqual(errors,[]);
  console.log('PASS education: minimal record, same editor, date conflict retains draft, no duplicate, fresh/reset and reload');
  await context.request.post(base+'/_column-test/family-geography');await page.locator('#tab-family').click();
  const family=page.locator('[data-additional-panel=family]'),ff=family.locator('form'),fe=family.locator('[data-additional-editor]');
  await family.locator('[data-additional-new]').click();await ff.locator('[name=kinship]').selectOption('daughter');await ff.locator('[name=full_name]').fill('Тестова Дитина');
  await ff.locator('[name=address_text]').fill('  Історична адреса\nБуд. 01  ');
  // Select a settlement first, then an unrelated region: independent IDs must survive.
  await ff.locator('[name=settlement]').fill('Старе місто родини');await ff.locator('[data-family-suggestions=settlement] button').first().click();
  const townId=await ff.locator('[name=settlement_id]').inputValue();assert.ok(townId);
  await ff.locator('[name=region]').fill('Інша область сім’ї');await ff.locator('[data-family-suggestions=region] button').first().click();assert.equal(await ff.locator('[name=settlement_id]').inputValue(),townId);
  await ff.locator('[name=phone]').fill('+380 (00) 000-00-00');await ff.locator('[data-exact-date-for=birth_on]').fill('15.05.1995');await ff.locator('[data-exact-date-for=death_on]').fill('14.05.1995');
  await ff.getByRole('button',{name:'Зберегти',exact:true}).click();await family.locator('[data-additional-message]').filter({hasText:'Дата смерті'}).waitFor();assert.equal(await ff.locator('[name=address_text]').inputValue(),'  Історична адреса\nБуд. 01  ');
  await ff.locator('[data-exact-date-for=death_on]').fill('');await ff.getByRole('button',{name:'Зберегти',exact:true}).click();await fe.waitFor({state:'hidden'});
  await family.locator('[data-additional-message]').filter({hasText:'не належить'}).waitFor();
  await family.locator('[data-additional-record]').evaluate(n=>n.open=true);await family.getByRole('button',{name:'Редагувати',exact:true}).click();
  assert.equal(await ff.locator('[name=settlement_id]').inputValue(),townId);assert.equal(await ff.locator('[name=address_text]').inputValue(),'  Історична адреса\nБуд. 01  ');
  // Only the edited field loses its own reference; another field is unaffected.
  const regionId=await ff.locator('[name=region_id]').inputValue();await ff.locator('[name=settlement]').fill('Невідоме село');assert.equal(await ff.locator('[name=settlement_id]').inputValue(),'');assert.equal(await ff.locator('[name=region_id]').inputValue(),regionId);
  await ff.locator('[name=region]').fill('');await ff.getByRole('button',{name:'Зберегти',exact:true}).click();await fe.waitFor({state:'hidden'});
  await family.locator('[data-additional-new]').click();await ff.locator('[name=kinship]').selectOption('daughter');await ff.locator('[name=full_name]').fill('Інша Дитина');await ff.getByRole('button',{name:'Зберегти',exact:true}).click();await fe.waitFor({state:'hidden'});
  assert.equal(await family.locator('[data-additional-record]').count(),2);await page.reload();await family.locator('[data-additional-record]').filter({hasText:'Невідоме село'}).waitFor();assert.deepEqual(errors,[]);
  console.log('PASS family: siblings, optional fields, exact dates, original address, real alias suggestions, mismatch and unknown, independent links and reload');
  await page.locator('#tab-directives').click();const directives=page.locator('[data-additional-panel=directives]'),df=directives.locator('form'),de=directives.locator('[data-additional-editor]');
  await directives.locator('[data-additional-new]').click();await df.getByRole('button',{name:'Зберегти',exact:true}).click();await directives.locator('[data-additional-message]').filter({hasText:'Вкажіть номер'}).waitFor();assert.equal(await de.isVisible(),true);
  await df.locator('[name=number]').fill('123/26');await df.locator('[data-exact-date-for=issued_on]').fill('31.10.2026');await df.getByRole('button',{name:'Зберегти',exact:true}).click();await de.waitFor({state:'hidden'});
  await directives.locator('[data-additional-record]').evaluate(n=>n.open=true);await directives.getByRole('button',{name:'Редагувати',exact:true}).click();assert.equal(await df.locator('[data-exact-date-for=issued_on]').inputValue(),'31.10.2026');await df.locator('[name=number]').fill('456/26');await df.getByRole('button',{name:'Зберегти',exact:true}).click();await de.waitFor({state:'hidden'});
  assert.equal(await directives.locator('[data-additional-record]').count(),1);assert.equal(await df.locator('[name=number]').getAttribute('maxlength'),'300');await page.reload();await directives.locator('[data-additional-record]').filter({hasText:'456/26'}).waitFor();assert.deepEqual(errors,[]);
  console.log('PASS directives: empty rejected, precise date, number limit, edit without duplicates, reset and reload');
  const id=await directives.locator('[data-additional-record]').first().getAttribute('data-additional-record');await page.goto(base+'/person_full_info/3#directives-'+id);
  const linked=page.locator(`[data-additional-panel=directives] [data-additional-record="${id}"]`);await linked.waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('#directives [data-additional-record]')?.open);
  assert.equal(new URL(page.url()).hash,'#directives-'+id);assert.equal(await page.locator('[data-additional-panel=directives] [data-additional-editor]').isVisible(),false);
  assert.deepEqual(errors,[]);console.log('PASS profile hash: record link activates the correct tab and opens the card without entering edit mode');
 }finally{await page.close();}
};

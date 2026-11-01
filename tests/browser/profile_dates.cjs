const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(base+'/person_full_info/1#dna');try{await page.locator('[data-medical-panel=dna] [data-medical-content]').waitFor({state:'visible'});}catch(e){console.log('DIAG',errors,await page.locator('[data-medical-panel=dna]').textContent(),await(await context.request.get(base+'/auth/me')).text());throw e;}
  const panel=page.locator('[data-medical-panel=dna]');await panel.locator('[data-medical-new]').click();
  const form=panel.locator('[data-medical-form]'),display=form.locator('[data-exact-date-for=collected_on]'),canonical=form.locator('[name=collected_on]');
  assert.equal(await display.getAttribute('placeholder'),'ДД.ММ.РРРР');assert.equal(await display.inputValue(),'');
  await display.pressSequentially('10');assert.equal(await display.inputValue(),'10.');
  await display.pressSequentially('06');assert.equal(await display.inputValue(),'10.06.');
  await display.pressSequentially('2025');assert.equal(await display.inputValue(),'10.06.2025');assert.equal(await canonical.inputValue(),'2025-06-10');
  await display.pressSequentially('99');assert.equal(await display.inputValue(),'10.06.2025');
  await display.fill('');await display.pressSequentially('10.06.2025');assert.equal(await display.inputValue(),'10.06.2025');
  await display.evaluate(n=>n.setSelectionRange(3,5));await display.pressSequentially('07');assert.equal(await display.inputValue(),'10.07.2025');assert.equal(await canonical.inputValue(),'2025-07-10');
  await display.fill('10');await display.press('Backspace');assert.equal(await display.inputValue(),'1');assert.equal(await canonical.inputValue(),'');
  await display.fill('10062025');await display.evaluate(n=>n.setSelectionRange(2,2));await display.press('Delete');assert.equal(await display.inputValue(),'10.62.025');
  await display.fill('10.06.2025');await display.press('Backspace');assert.equal(await display.inputValue(),'10.06.202');assert.equal(await display.evaluate(n=>n.checkValidity()),false);
  await display.fill('100');assert.doesNotMatch(await display.evaluate(n=>n.validationMessage),/коректну повну/);
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();assert.equal(await panel.locator('[data-medical-editor]').isVisible(),true);assert.equal(await canonical.inputValue(),'');
  // Paste through the browser clipboard rather than a programmatic assignment.
  await context.grantPermissions(['clipboard-read','clipboard-write']);await page.evaluate(()=>navigator.clipboard.writeText('10.06.2025'));await display.selectText();await display.press('Control+V');assert.equal(await display.inputValue(),'10.06.2025');assert.equal(await canonical.inputValue(),'2025-06-10');
  console.log('PASS date mask: digits/dots, eight-digit limit, selection edits, Backspace/Delete, paste and incomplete-date blocking');
  await display.fill('31.10.2026');assert.equal(await canonical.inputValue(),'2026-10-31');
  await display.fill('29.02.2025');assert.equal(await display.evaluate(n=>n.checkValidity()),false);assert.equal(await display.inputValue(),'29.02.2025');
  await display.fill('29.02.2024');assert.equal(await canonical.inputValue(),'2024-02-29');
  await form.locator('[data-date-calendar]').evaluate(n=>{n.value='2026-11-05';n.dispatchEvent(new Event('change',{bubbles:true}));});assert.equal(await display.inputValue(),'05.11.2026');
  await form.locator('[name=envelope_number]').fill('DATE-001');await form.getByRole('button',{name:'Зберегти',exact:true}).click();await panel.locator('[data-medical-editor]').waitFor({state:'hidden'});
  const card=panel.locator('[data-medical-record]');assert.match(await card.innerText(),/05.11.2026/);assert.doesNotMatch(await card.innerText(),/2026-11-05/);
  await card.locator('summary').first().click();await card.getByRole('button',{name:'Редагувати',exact:true}).click();assert.equal(await display.inputValue(),'05.11.2026');
  await display.fill('');assert.equal(await canonical.inputValue(),'');
  await page.reload();await panel.locator('[data-medical-content]').waitFor({state:'visible'});assert.match(await panel.locator('[data-medical-record]').innerText(),/05.11.2026/);
  console.log('PASS profile dates: en-US-friendly DMY keyboard/calendar, leap validation, ISO API and edit/reload');

  await page.locator('#tab-exams').click();
  const exams=page.locator('[data-medical-panel=exams]');await exams.locator('[data-medical-new]').click();
  const examForm=exams.locator('[data-medical-form]'),issued=examForm.locator('[data-exact-date-for=issued_on]');
  await examForm.locator('[name=basis_note]').fill('Тестова рекомендація лікаря');
  await examForm.locator('[name=status]').selectOption('COMPLETED');await issued.fill('31.02.2026');
  assert.equal(await issued.evaluate(n=>n.checkValidity()),false);
  await examForm.locator('[name=status]').selectOption('NEEDS_EXAM');
  assert.equal(await issued.isVisible(),false);assert.equal(await issued.isDisabled(),true);
  assert.equal(await examForm.locator('[name=issued_on]').isDisabled(),true);
  assert.equal(await issued.inputValue(),'31.02.2026');
  assert.equal(await examForm.evaluate(n=>n.checkValidity()),true);
  await examForm.getByRole('button',{name:'Зберегти',exact:true}).click();
  await exams.locator('[data-medical-editor]').waitFor({state:'hidden'});
  assert.equal(await exams.locator('[data-medical-record]').count(),1);
  console.log('PASS profile dates: hidden invalid exam fields retain their draft without blocking another state');

  await page.locator('#tab-ranks').click();
  const rankTrigger=page.locator('#ranks [data-bs-target="#addNewRank"]'),rankModal=page.locator('#addNewRank');
  await rankTrigger.click();await rankModal.waitFor({state:'visible'});
  const rankForm=rankModal.locator('form'),day=rankForm.locator('[data-date-part=day]');
  await day.fill('31');await rankForm.locator('[data-date-part=month]').fill('2');
  assert.equal(await day.evaluate(n=>n.checkValidity()),false);
  await rankForm.locator('[name=rank_order_number]').fill('Unsaved draft');
  await rankModal.locator('.btn-close').click();await rankModal.waitFor({state:'hidden'});
  await rankTrigger.click();await rankModal.waitFor({state:'visible'});
  assert.equal(await day.inputValue(),'');assert.equal(await day.evaluate(n=>n.checkValidity()),true);
  assert.equal(await rankForm.locator('[name=rank_order_number]').inputValue(),'');
  assert.equal(await rankForm.locator('[data-date-input]').evaluate(n=>n.dataset.dateReady),'true');
  await rankModal.locator('.btn-close').click();await rankModal.waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);console.log('PASS profile dates: reopening a new rank clears invalid partial-date state and the abandoned draft');
 }finally{await page.close();}
};

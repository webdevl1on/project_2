const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const panel=kind=>page.locator(`[data-medical-panel="${kind}"]`),form=kind=>panel(kind).locator('[data-medical-form]');
 const tab=async kind=>page.locator(`#tab-${kind}`).click();
 const records=kind=>panel(kind).locator('[data-medical-record]');
 const newRecord=async kind=>{await tab(kind);const details=panel(kind).locator('[data-medical-editor]');if(!await details.evaluate(n=>n.open))await details.locator('summary').click();await panel(kind).locator('[data-medical-new]').click();};
 const save=async kind=>{await form(kind).locator('button').filter({hasText:/^Зберегти$/}).click();await panel(kind).locator('[data-medical-message]').filter({hasText:/^Збережено/}).waitFor();};
 const scenario=async(name,fn)=>{await fn();console.log('PASS medical: '+name);};
 try{
  await context.request.post(base+'/_column-test/documents/setup');await page.goto(base+'/person_full_info/1');
  await scenario('personal GUI login guards medical records and preserves existing profile',async()=>{
   await tab('injuries');const login=panel('injuries').locator('[data-medical-auth]');await login.locator('[name=username]').fill('doc-admin');await login.locator('[name=password]').fill(adminToken);await login.locator('button').click();await panel('injuries').locator('[data-medical-content]').waitFor({state:'visible'});
   assert.equal(await page.locator('#tab-service-history').count(),1);assert.equal(await page.locator('#tab-contacts').count(),1);
  });
  await scenario('injury independent of exams, automatic task exists once and linked sections work',async()=>{
   await newRecord('injuries');await form('injuries').locator('[name=description]').fill('Синтетичне поранення');await form('injuries').locator('[name=exam_not_needed]').check();await save('injuries');assert.equal(await records('injuries').count(),1);
   await form('injuries').locator('[name=area]').fill('Тестовий район');await save('injuries');await tab('tasks');assert.equal(await records('tasks').count(),1);assert.match(await records('tasks').innerText(),/Відкрите/);
   assert.equal(await records('exams').count(),0);assert.equal(await records('awards').count(),0);
  });
  await scenario('planned and completed exams, ambiguity, manual selection, automatic reset and overview',async()=>{
   await newRecord('exams');await form('exams').locator('[name=status]').selectOption('PLANNED');await form('exams').locator('[name=basis]').selectOption('INJURY');await form('exams').locator('[name=injury_id]').selectOption('1');await save('exams');
   await tab('tasks');assert.match(await panel('tasks').locator('[data-pending-exams]').innerText(),/Непройдені ВЛК: 1/);
   await newRecord('exams');await form('exams').locator('[name=status]').selectOption('COMPLETED');await form('exams').locator('[name=basis]').selectOption('ILLNESS');await form('exams').locator('[name=issued_on]').fill('2026-05-01');await form('exams').locator('[name=fitness]').selectOption('FIT_SUPPORT');await save('exams');
   assert.match(await panel('exams').locator('[data-active-exam]').innerText(),/Придатний до служби/);
   await newRecord('exams');await form('exams').locator('[name=status]').selectOption('COMPLETED');await form('exams').locator('[name=issued_on]').fill('2026-05-01');await form('exams').locator('[name=fitness]').selectOption('UNFIT');await save('exams');assert.match(await panel('exams').locator('[data-active-exam]').innerText(),/не визначено/);
   await records('exams').filter({hasText:'Запис №2'}).getByRole('button',{name:'Зробити активним',exact:true}).click();await panel('exams').locator('[data-active-exam]').filter({hasText:'ручний вибір'}).waitFor();
   await tab('general');await page.locator('#profile-overview').filter({hasText:'Придатний до служби'}).waitFor();
   await tab('exams');await panel('exams').locator('[data-exam-auto]').click();await panel('exams').locator('[data-active-exam]').filter({hasText:'не визначено'}).waitFor();
  });
  await scenario('award status alone never closes task; evidence errors preserve form then confirmed report closes task',async()=>{
   await newRecord('awards');await form('awards').locator('[name=name]').fill('Тестова нагорода');await form('awards').locator('[name=injury_id]').selectOption('1');await form('awards').locator('[name=status]').selectOption('NOT_APPROPRIATE');await save('awards');await tab('tasks');assert.match(await records('tasks').innerText(),/Відкрите/);
   await tab('awards');await form('awards').locator('[name=refusal_confirmed]').check();await form('awards').locator('button').filter({hasText:/^Зберегти$/}).click();await panel('awards').locator('[data-medical-message]').filter({hasText:/рапорт потребує/}).waitFor();assert.equal(await form('awards').locator('[name=name]').inputValue(),'Тестова нагорода');assert.equal(await form('awards').locator('[name=refusal_confirmed]').isChecked(),true);assert.equal(await panel('awards').locator('[data-medical-editor]').evaluate(n=>n.open),true);
   await form('awards').locator('[name=refusal_on]').fill('2026-06-01');await form('awards').locator('[name=refusal_number]').fill('0001');await form('awards').locator('[name=refusal_reason]').fill('Тестова причина');await save('awards');await tab('tasks');assert.match(await records('tasks').innerText(),/Завершене/);
   await records('tasks').getByRole('button',{name:'Редагувати',exact:true}).click();await form('tasks').locator('[name=status]').selectOption('CANCELLED');await form('tasks').locator('[name=decision_reason]').fill('Ручне рішення');await save('tasks');assert.match(await panel('tasks').locator('[data-pending-exams]').innerText(),/ручне рішення/);
  });
  await scenario('multiple categorized protected copies reuse existing documents and audit',async()=>{
   await tab('injuries');let card=records('injuries').first();await card.locator('summary').filter({hasText:'Документи та копії'}).click();await card.locator('select[name=category]').selectOption('form100');await card.getByRole('button',{name:'Додати документ',exact:true}).click();
   await card.getByText('Форма 100 · документ №1',{exact:true}).waitFor();
   await card.locator('input[type=file]').setInputFiles({name:'front.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.7 synthetic')});await card.getByRole('button',{name:'Додати копію',exact:true}).click();await card.getByText('front.pdf',{exact:true}).waitFor();
   await card.locator('input[type=file]').setInputFiles({name:'back.png',mimeType:'image/png',buffer:Buffer.from([137,80,78,71,13,10,26,10,0])});await card.getByRole('button',{name:'Додати копію',exact:true}).click();await card.getByText('back.png',{exact:true}).waitFor();
   assert.equal((await context.request.get(base+'/persons/1/documents/files/1')).status(),200);assert.notEqual((await context.request.get(base+'/persons/2/documents/files/1')).status(),200);
   await tab('tasks');await panel('tasks').getByText('Журнал змін',{exact:true}).click();assert.match(await panel('tasks').locator('[data-medical-audit]').innerText(),/document_link/);
  });
  await scenario('DNA history persists and medical table fields use common visibility and filtering',async()=>{
   await newRecord('dna');await form('dna').locator('[name=envelope_number]').fill('0000123');await form('dna').locator('[name=collected_on]').fill('2026-06-01');await form('dna').locator('[name=storage_unit]').fill('Тестова частина');await save('dna');await page.reload();await records('dna').filter({hasText:'0000123'}).waitFor();
   await page.goto(base+'/person-positions');await page.evaluate(()=>{const c=TableColumns.controllers.get('person-positions');c.commitLayout({visible:['row_number','medical_fitness','pending_exam_count','dna_envelope_number'],order:c.state.layout.order});});
   assert.equal(await page.locator('#person-positions tbody tr').count(),3);assert.match(await page.locator('[data-row-key="position:1"] [data-column-key="dna_envelope_number"]').innerText(),/0000123/);
   const response=await context.request.get(base+'/person-positions?pending_exam_count=1&filter_order=pending_exam_count');assert.equal(response.status(),200);assert.match(await response.text(),/Синтетичне|person-positions/);
   assert.deepEqual(errors,[]);
  });
 }finally{await page.close();}
};

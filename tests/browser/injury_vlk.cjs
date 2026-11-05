const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const panel=k=>page.locator(`[data-medical-panel=${k}]`),tab=async k=>page.locator(`#tab-${k}`).click();
 const task=()=>panel('tasks').locator('[data-task-kind=injury_vlk]');
 const save=async k=>{if(k==='exams'){const f=panel(k).locator('[data-medical-form]'),s=await f.locator('[name=status]').inputValue();if(s==='PLANNED')await f.locator('[data-exact-date-for=planned_on]').fill('01.01.2026');if(s==='COMPLETED'){await f.locator('[data-exact-date-for=issued_on]').fill('03.01.2026');await f.locator('[name=number]').fill('001');await f.locator('[name=fitness]').selectOption('FIT');}}await panel(k).locator('[data-medical-form]').getByRole('button',{name:'Зберегти',exact:true}).click();await panel(k).locator('[data-medical-editor]').waitFor({state:'hidden'});await page.locator('[data-profile-toast]').filter({hasText:/Запис додано|Зміни збережено/}).waitFor();};
 try{
  await context.request.post(base+'/_column-test/documents/setup');await page.goto(base+'/person_full_info/1#injuries');
  await panel('injuries').locator('[data-medical-content]').waitFor({state:'visible'});
  await panel('injuries').locator('[data-medical-new]').click();
  assert.equal(await panel('injuries').locator('[name=exam_not_needed]').count(),0);
  await panel('injuries').locator('[name=description]').fill('Синтетичне поранення');await save('injuries');
  await tab('tasks');assert.equal(await task().count(),1);assert.match(await task().innerText(),/Очікує рішення щодо ВЛК/);
  console.log('PASS injury VLK: registration creates decision task without choosing or creating an exam');
  await task().locator(':scope > [data-record-card] > summary').click();page.once('dialog',d=>d.accept(''));await task().getByRole('button',{name:'ВЛК не потрібна',exact:true}).click();await panel('tasks').locator('[data-medical-message]').filter({hasText:/Вкажіть причину/}).waitFor();
  assert.equal(await task().count(),1);
  page.once('dialog',d=>d.accept('Тестова медична причина'));await task().getByRole('button',{name:'ВЛК не потрібна',exact:true}).click();await panel('tasks').locator('[data-medical-message]').filter({hasText:'Рішення щодо ВЛК збережено'}).waitFor();assert.equal(await task().count(),0);
  await panel('tasks').locator('[data-task-history]').check();await task().locator(':scope > [data-record-card] > summary').click();assert.match(await task().innerText(),/Завершено: ВЛК не потрібна/);assert.match(await task().innerText(),/Тестова медична причина/);
  await tab('injuries');assert.match(await panel('injuries').locator('[data-medical-record]').innerText(),/Завершено: ВЛК не потрібна/);
  await tab('tasks');page.once('dialog',d=>d.accept('Виправлення помилки'));await task().getByRole('button',{name:'Скасувати рішення «ВЛК не потрібна»',exact:true}).click();await panel('tasks').locator('[data-medical-message]').filter({hasText:/Рішення скасовано/}).waitFor();
  console.log('PASS injury VLK: reason is required; completed decision stays in history and is explicitly reversible');
  await task().getByRole('button',{name:'Відкрити ВЛК',exact:true}).click();await panel('exams').waitFor({state:'visible'});
  const form=panel('exams').locator('[data-medical-form]');assert.equal(await form.locator('[name=basis]').inputValue(),'INJURY');assert.equal(await form.locator('[name=injury_id]').inputValue(),'1');assert.equal(await form.locator('[name=status]').inputValue(),'NEEDS_EXAM');
  await save('exams');await tab('tasks');assert.match(await task().innerText(),/Очікує проходження ВЛК/);assert.equal(await task().getByRole('link',{name:/ВЛК №1/}).count(),1);
  await task().getByRole('link',{name:/ВЛК №1/}).click();await panel('exams').waitFor({state:'visible'});await panel('exams').locator('[data-medical-record]').first().getByRole('button',{name:'Редагувати',exact:true}).click();await form.locator('[name=status]').selectOption('PLANNED');await save('exams');await tab('tasks');assert.match(await task().innerText(),/Очікує проходження ВЛК/);
  await task().getByRole('link',{name:/ВЛК №1/}).click();await panel('exams').waitFor({state:'visible'});await panel('exams').locator('[data-medical-record]').first().getByRole('button',{name:'Редагувати',exact:true}).click();await form.locator('[name=status]').selectOption('COMPLETED');await save('exams');await tab('tasks');assert.match(await task().innerText(),/Завершено: ВЛК пройдено/);
  await task().getByRole('link',{name:/ВЛК №1/}).click();await panel('exams').waitFor({state:'visible'});await panel('exams').locator('[data-medical-record]').first().getByRole('button',{name:'Редагувати',exact:true}).click();await form.locator('[name=status]').selectOption('NEEDS_EXAM');await save('exams');await tab('tasks');assert.match(await task().innerText(),/Очікує проходження ВЛК/);
  assert.equal(await task().count(),1);assert.deepEqual(errors,[]);
  console.log('PASS injury VLK: prefill, planned/completed transitions and reopening preserve one task');
 }finally{await page.close();}
};

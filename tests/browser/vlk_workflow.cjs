const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const p=()=>page.locator('[data-medical-panel=exams]'),f=()=>p().locator('[data-medical-form]'),records=()=>p().locator('[data-medical-record]');
 const fresh=async()=>p().locator('[data-medical-new]').click();
 const save=async(edit=false)=>{await f().getByRole('button',{name:'Зберегти',exact:true}).click();await p().locator('[data-medical-message]').filter({hasText:edit?'Зміни збережено':'Запис створено'}).waitFor();};
 const edit=async id=>{const card=p().locator(`[data-medical-record="${id}"]`);const details=card.locator('[data-exam-card]');if(!await details.evaluate(n=>n.open))await details.locator(':scope > summary').click();await card.getByRole('button',{name:'Редагувати',exact:true}).click();};
 try{
  await context.request.post(base+'/_column-test/documents/setup');await page.goto(base+'/person_full_info/1#exams');
  const login=p().locator('[data-medical-auth]');await login.locator('[name=username]').fill('doc-admin');await login.locator('[name=password]').fill(adminToken);await login.locator('button').click();await p().locator('[data-medical-content]').waitFor({state:'visible'});
  await fresh();assert.equal(await f().locator('[name=status] option[value=INTERRUPTED]').evaluate(n=>n.disabled),true);
  assert.equal(await f().locator('[name=issued_on]').isVisible(),false);await f().locator('[name=basis_note]').fill('Захворювання');await save();
  assert.equal(await p().locator('[data-medical-editor]').evaluate(n=>n.open),false);assert.equal(await f().locator('[name=basis_note]').inputValue(),'');assert.equal(await f().getAttribute('data-key'),null);
  assert.equal(await page.locator('[data-medical-toast]').isVisible(),true);assert.equal(await records().locator('[data-exam-card]').evaluateAll(nodes=>nodes.every(n=>!n.open)),true);
  console.log('PASS VLK workflow: conditional creation, interrupted disabled, toast, cleared collapsed editor');
  await fresh();await f().locator('[name=status]').selectOption('PLANNED');await f().locator('[name=planned_on]').fill('2035-01-02');await f().locator('[name=basis_note]').fill('Повторний огляд');await save();
  await edit(2);await f().locator('[name=status]').selectOption('INTERRUPTED');assert.equal(await f().locator('[name=interrupted_on]').isVisible(),true);assert.equal(await f().locator('[name=fitness]').isVisible(),false);
  await f().locator('[name=interrupted_on]').fill('2035-01-01');await f().locator('[name=interruption_reason]').fill('Перервано');await f().getByRole('button',{name:'Зберегти',exact:true}).click();await p().locator('[data-medical-message]').filter({hasText:'послідовність'}).waitFor();
  assert.equal(await p().locator('[data-medical-editor]').evaluate(n=>n.open),true);assert.equal(await f().locator('[name=interruption_reason]').inputValue(),'Перервано');
  await f().locator('[name=interrupted_on]').fill('2035-01-03');await save(true);
  assert.match(await p().locator('[data-medical-record="2"] > details > summary').innerText(),/ВЛК перервано.*2035-01-03/);
  console.log('PASS VLK workflow: interruption only after planning, date errors retain the draft');
  await fresh();await f().locator('[name=status]').selectOption('COMPLETED');assert.equal(await f().locator('[name=number]').isVisible(),true);
  await f().locator('[name=planned_on]').fill('2035-02-01');await f().locator('[name=ended_on]').fill('2035-02-04');await f().locator('[name=issued_on]').fill('2035-02-06');await f().locator('[name=number]').fill('0003');await f().locator('[name=fitness]').selectOption('FIT_SUPPORT');await save();
  const summary=p().locator('[data-medical-record="3"] > details > summary');assert.match(await summary.innerText(),/2035-02-01.*2035-02-04.*0003.*Обмежено придатний.*Актуальне ВЛК/);
  assert.deepEqual(await records().evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.medicalRecord))),[2,1,3]);
  await page.locator('#tab-tasks').click();assert.equal(await page.locator('[data-medical-panel=tasks] [data-task-kind=exam_vlk]').count(),2);
  await page.locator('#tab-exams').click();await edit(2);assert.equal(await f().locator('[name=status] option[value=PLANNED]').evaluate(n=>n.disabled),true);
  assert.deepEqual(errors,[]);console.log('PASS VLK workflow: separate future dates, compact fitness, active badge, stable order and standalone controls');
 }finally{await page.close();}
};

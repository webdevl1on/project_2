const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await context.request.post(base+'/_column-test/documents/setup');
  await page.goto(base+'/person_full_info/1#exams');
  const panel=page.locator('[data-medical-panel=exams]');
  await panel.locator('[data-medical-content]').waitFor({state:'visible'});
  assert.equal(await panel.locator('[data-medical-login]').isHidden(),true);
  assert.match(await panel.locator('[data-dev-auth-warning]').innerText(),/авторизацію вимкнено/);
  console.log('PASS dev auth: no login, visible development warning');
  await panel.locator('[data-medical-editor] summary').click();
  const form=panel.locator('[data-medical-form]');await form.locator('[name=basis]').selectOption('ILLNESS');
  await form.getByRole('button',{name:'Зберегти',exact:true}).click();
  await panel.locator('[data-medical-message]').filter({hasText:/Збережено/}).waitFor();
  await form.locator('[name=basis_note]').fill('Тестове уточнення');await form.getByRole('button',{name:'Зберегти',exact:true}).click();
  await panel.locator('[data-medical-record]').filter({hasText:'Тестове уточнення'}).waitFor();
  const result=await page.evaluate(async()=>{
   const me=await(await fetch('/auth/me')).json();
   const data=await(await fetch('/persons/1/medical')).json();return {me,data};
  });
  assert.equal(result.me.dev_auth_bypass,true);assert.ok(result.data.audit.every(r=>r.actor_id===result.me.id));
  assert.deepEqual(errors,[]);console.log('PASS dev auth: create/edit and real audited test actor without password');
 }finally{await page.close();}
};

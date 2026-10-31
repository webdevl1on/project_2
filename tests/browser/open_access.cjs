const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(base+'/person_full_info/1#exams');
  const panel=page.locator('[data-medical-panel=exams]');await panel.locator('[data-medical-content]').waitFor({state:'visible'});
  assert.equal(await panel.locator('[data-medical-login]').isHidden(),true);
  assert.match(await panel.locator('[data-dev-auth-warning]').innerText(),/вільний доступ/);
  await panel.locator('[data-medical-editor] summary').click();
  await panel.locator('[name=basis]').selectOption('ILLNESS');await panel.locator('[name=basis_note]').fill('Тестова підстава');await panel.locator('[data-medical-form]').getByRole('button',{name:'Зберегти',exact:true}).click();
  await panel.locator('[data-medical-message]').filter({hasText:/Запис створено|Зміни збережено/}).waitFor();
  const me=await (await context.request.get(base+'/auth/me')).json();assert.ok(me.open_access);assert.equal(me.role,'admin');
  console.log('PASS open access: medical UI opens and saves without login');
  await page.goto(base+'/admin/login');assert.equal(page.url(),base+'/admin');
  assert.equal((await context.request.get(base+'/admin/tcc')).status(),200);
  assert.equal((await context.request.get(base+'/persons/1/documents')).status(),200);
  console.log('PASS open access: admin, TCC and documents require no token or login');
  assert.deepEqual(errors,[]);
 }finally{await page.close();}
};

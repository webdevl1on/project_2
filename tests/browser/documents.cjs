const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(), errors=[];page.on('pageerror',e=>errors.push(e.message));
 await context.clearCookies();
 try {
  await context.request.post(base+'/_column-test/documents/setup');
  await page.goto(base+'/person_full_info/3');
  const run=async(path,data,csrf)=>page.evaluate(async({path,data,csrf})=>{
   const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{})},body:data===undefined?undefined:JSON.stringify(data)});
   return {status:response.status,data:await response.json()};
  },{path,data,csrf});
  assert.equal((await run('/persons/3/documents')).status,401);
  const login=await run('/auth/login',{username:'doc-admin',password:adminToken});assert.equal(login.status,200);
  const csrf=login.data.csrf_token;
  assert.equal((await run('/persons/3/documents',{type:'other',details:{number:'0001'}})).status,403);
  const created=await run('/persons/3/documents',{type:'other',details:{number:'0001'}},csrf);assert.equal(created.status,200);
  console.log('PASS documents: personal browser login is required and CSRF protects writes');
  let list=(await run('/persons/3/documents?code=other')).data.documents, record=list.find(r=>r.id===created.data.id);
  assert.equal(record.presence,'UNKNOWN');assert.equal(record.automatic_status,'FILLED');assert.equal(record.has_copies,false);
  const upload=await page.evaluate(async({id,revision,csrf})=>{
   const form=new FormData();form.set('file',new Blob(['%PDF-1.7 synthetic'],{type:'application/pdf'}),'front.pdf');form.set('side','front');form.set('revision',revision);
   const response=await fetch(`/persons/3/documents/${id}/files`,{method:'POST',body:form,headers:{'X-CSRF-Token':csrf}});return {status:response.status,data:await response.json()};
  },{id:record.id,revision:record.revision,csrf});
  assert.equal(upload.status,200);
  record=(await run('/persons/3/documents?code=other')).data.documents.find(r=>r.id===record.id);
  assert.equal(record.has_copies,true);assert.equal(record.presence,'UNKNOWN');
  assert.equal((await context.request.get(base+`/persons/3/documents/files/${upload.data.id}`)).status(),200);
  console.log('PASS documents: protected copy upload does not alter physical presence or completeness');
  assert.equal((await run(`/persons/3/documents/${record.id}/override`,{revision:record.revision,status:'NOT_FILLED',reason:'Тестова ручна перевірка'},csrf)).status,200);
  const after=(await run('/persons/3/documents?code=other')).data.documents.find(r=>r.id===record.id);
  assert.equal(after.automatic_status,'FILLED');assert.equal(after.effective_status,'NOT_FILLED');assert.equal(after.values.number,'0001');
  const journal=(await run('/persons/3/documents/audit')).data.entries;
  assert.ok(journal.some(e=>e.operation==='override'&&e.actor_id===1&&e.reason==='Тестова ручна перевірка'));
  assert.equal((await run('/auth/logout',{},csrf)).status,200);
  assert.equal((await context.request.get(base+`/persons/3/documents/files/${upload.data.id}`)).status(),401);
  assert.deepEqual(errors,[]);
  console.log('PASS documents: manual status leaves data intact, records the real actor and logout revokes file access');
 }finally{await page.close();}
};

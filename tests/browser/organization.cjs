/* Existing harness supplies a real Master/Admin MFA session and isolated fixture DB. */
const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 const api=async(path,data)=>{const response=await context.request.post(base+path,{data});assert.equal(response.status(),200,await response.text());return response.json();};
 const tree=async on=>(await(await context.request.get(base+'/admin/organization/tree?on='+on)).json());
 const select=async id=>{await page.locator('[data-org-expand]').click();await page.locator(`[data-org-select="${id}"]`).click();await page.waitForFunction(id=>document.querySelector('[data-org-unit-id]')?.textContent==='ID '+id,id);};
 const form=action=>page.locator(`[data-org-form="${action}"]`),date=(scope,key)=>scope.locator(`[data-exact-date-for="${key}"]`);
 const open=async action=>{const details=form(action).locator('..');if(!await details.evaluate(node=>node.open))await details.locator(':scope > summary').click();};
 async function save(action){await Promise.all([page.waitForResponse(response=>response.request().method()==='POST'&&response.url().includes('/admin/organization/')),form(action).locator('button:not([type=button])').click()]);await page.waitForFunction(action=>document.querySelector(`[data-org-form="${action}"]`)?.dataset.pending!=='1',action);}
 async function createUI(name,kind){await open('create');await form('create').locator('[name=kind]').selectOption(kind);await form('create').locator('[name=name]').fill(name);await date(form('create'),'formed_on').fill('01.01.2020');await save('create');return Number(new URL(page.url()).searchParams.get('unit_id'));}
 try{
  await page.goto(base+'/admin/organization?on=2020-06-01');await page.locator('[data-org-tree]').waitFor({state:'attached'});
  const root=await createUI('Тестова рота А','company');assert.ok(root);assert.match(await page.locator('[data-org-title]').innerText(),/Тестова рота А/);
  const other=(await api('/admin/organization/units',{name:'Тестова рота Б',kind:'company',formed_on:'2020-01-01'})).unit_id;
  await page.goto(base+'/admin/organization?on=2020-06-01&unit_id='+root);await page.locator('[data-org-selected]:visible').waitFor();
  await form('name').locator('[name=name]').fill('Тестова рота Б');await date(form('name'),'effective_from').fill('01.02.2020');const before=await form('name').evaluate(node=>[...new FormData(node)]);await save('name');
  await form('name').locator('[data-org-error]:visible').waitFor();assert.deepEqual(await form('name').evaluate(node=>[...new FormData(node)]),before);assert.equal(await form('name').locator('..').evaluate(node=>node.open),true);
  await form('name').locator('[name=name]').fill('Уточнена рота А');await save('name');assert.match(await page.locator('[data-org-title]').innerText(),/Уточнена рота А/);
  console.log('PASS organization: standalone creation, shared date inputs and duplicate-name error retain the open form and draft');

  await page.locator('[data-org-create-parent]').click();const parent=await createUI('Батальйон пізнішого додавання','battalion');
  await page.waitForFunction(root=>document.querySelector('[data-org-unit-id]')?.textContent==='ID '+root,root);
  const parentId=Number(await form('parent').locator('[name=parent_id]').inputValue());assert.ok(parentId&&parentId!==root);
  await date(form('parent'),'effective_from').fill('01.03.2020');await save('parent');
  assert.equal((await tree('2020-02-29')).units.find(unit=>unit.id===root).parent_id,null);assert.equal((await tree('2020-03-01')).units.find(unit=>unit.id===root).parent_id,parentId);
  console.log('PASS organization: later parent creation requires a separate effective-date reparent action and preserves earlier history');

  let deep=other;for(let level=5;level<=7;level++)deep=(await api('/admin/organization/units',{name:'Рівень '+level,kind:'other',hierarchy_level:level,formed_on:'2020-01-01',parent_id:deep})).unit_id;
  const childA=(await api('/admin/organization/units',{name:'Перший взвод',kind:'platoon',formed_on:'2020-01-01',parent_id:root})).unit_id;
  const childB=(await api('/admin/organization/units',{name:'Другий взвод',kind:'platoon',formed_on:'2020-01-01',parent_id:root})).unit_id;
  await page.goto(base+'/admin/organization?on=2020-06-01&unit_id='+root);await page.locator('[data-org-expand]').click();assert.equal(await page.locator(`[data-org-select="${deep}"]`).isVisible(),true);
  const old=await tree('2020-06-01'),revisions=Object.fromEntries(old.units.filter(unit=>unit.parent_id===root).map(unit=>[unit.id,unit.revision]));
  await Promise.all([page.waitForResponse(response=>response.url().endsWith('/admin/organization/reorder')&&response.request().method()==='POST'),page.locator(`[data-org-unit="${childB}"] [data-org-drag]`).dragTo(page.locator(`[data-org-unit="${childA}"] > details > summary`),{targetPosition:{x:35,y:3}})]);
  await page.waitForFunction(()=>!document.querySelector('[data-org-message]')?.hidden);let current=await tree('2020-06-01');assert.equal(current.units.find(unit=>unit.id===childB).parent_id,root);assert.ok(current.units.find(unit=>unit.id===childB).sort_order<current.units.find(unit=>unit.id===childA).sort_order);
  const stale=await context.request.post(base+'/admin/organization/reorder',{data:{on:'2020-06-01',parent_id:root,ids:[childA,childB],revisions}});assert.equal(stale.status(),409);
  const cross=await context.request.post(base+'/admin/organization/reorder',{data:{on:'2020-06-01',parent_id:root,ids:[childA,other],revisions:{[childA]:1,[other]:1}}});assert.equal(cross.status(),409);
  console.log('PASS organization: full permitted-depth rendering and sibling Drag & Drop preserve parents; stale and cross-parent reorder are rejected');

  await select(childA);await open('operational');await form('operational').locator('[name=parent_id]').selectOption(String(other));await date(form('operational'),'valid_from').fill('01.05.2020');await save('operational');current=await tree('2020-06-01');assert.equal(current.units.find(unit=>unit.id===childA).parent_id,root);assert.ok(current.units.find(unit=>unit.id===childA).operational_parent_ids.includes(other));
  await open('name');await form('name').locator('[name=name]').fill('Незбережена чернетка');await date(form('name'),'effective_from').fill('31.02.2020');await form('name').locator('button:not([type=button])').click();assert.equal(await form('name').locator('[name=name]').inputValue(),'Незбережена чернетка');assert.equal(new URL(page.url()).searchParams.get('unit_id'),String(childA));
  await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  console.log('PASS organization: operational links remain separate, incomplete-calendar edits keep drafts, and the editor fits a narrow viewport');

  await select(childA);await page.locator('[data-org-create-child]').click();
  assert.equal(await form('create').locator('[name=kind] option[value=regiment]').evaluate(n=>n.disabled&&n.hidden),true);
  await form('create').locator('[name=kind]').selectOption('other');await form('create').locator('[name=hierarchy_level]').selectOption('6');await form('create').locator('[name=name]').fill('Інший з явним рівнем');await date(form('create'),'formed_on').fill('01.01.2020');await save('create');
  assert.equal((await tree('2020-06-01')).units.find(u=>u.name==='Інший з явним рівнем').hierarchy_level,6);
  console.log('PASS organization: child creation filters types and accepts an explicit valid other-unit level');

  await api('/auth/users',{username:'org-browser-viewer',display_name:'Тестовий спостерігач дерева',role:'user',password:adminToken});
  const raw=await browserContextNoMfa(context,base);try{assert.equal((await raw.request.get(base+'/admin/organization')).status(),401);}finally{await raw.close();}
  const noCsrf=await page.evaluate(async()=>{const response=await fetch('/admin/organization/reorder',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':'wrong'},body:'{}'});return response.status;});assert.equal(noCsrf,403);
  await context.clearCookies();assert.equal((await context.request.post(base+'/auth/login',{data:{username:'org-browser-viewer',password:adminToken}})).status(),200);assert.equal((await context.request.get(base+'/admin/organization')).status(),403);assert.equal((await context.request.post(base+'/admin/organization/units',{data:{name:'Заборонено',kind:'company',formed_on:'2020-01-01'}})).status(),403);
  assert.deepEqual(errors,[]);console.log('PASS organization: anonymous, Viewer and wrong-CSRF requests cannot administer the tree');
 }finally{await page.close();}
};
async function browserContextNoMfa(context){return context.browser().newContext();}

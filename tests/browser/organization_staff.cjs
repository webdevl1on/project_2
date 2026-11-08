/* The existing harness supplies a real MFA session and a temporary fixture database. */
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
function workbook(rows){return execFileSync(process.env.PYTHON||'python3',['-c',"import json,sys;from tests.test_organization_import import excel;sys.stdout.buffer.write(excel(json.load(sys.stdin)))"],{input:JSON.stringify(rows)});}
module.exports=async({context,base})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 const api=async(path,data)=>{const r=await context.request.post(base+path,{data});assert.equal(r.status(),200,await r.text());return r.json();};
 const form=selector=>page.locator(selector),preview=form('[data-staff-preview]'),confirm=form('[data-staff-confirm]');
 const date=(f,key)=>f.locator(`[data-exact-date-for="${key}"]`);
 async function submit(f,path,{reload=false}={}){const waiting=reload?page.waitForNavigation():page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes(path));const [response]=await Promise.all([waiting,f.locator('button:not([type=button])').click()]);return response;}
 async function upload(rows,mode,name=''){
  await preview.locator('[name=mode]').selectOption(mode);await preview.locator('[name=name]').fill(name);await date(preview,'on').fill('01.01.2026');
  await preview.locator('[name=file]').setInputFiles({name:'staff.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:workbook(rows)});
  const r=await submit(preview,'/preview');assert.equal(r.status(),200,await r.text());await page.locator('[data-preview-panel]:visible').waitFor();
 }
 async function receipt(){return Number((await page.locator('[data-preview-summary]').innerText()).match(/Квитанція ID (\d+)/)[1]);}
 try{
  const make=async(name,kind,parent_id)=> (await api('/admin/organization/units',{name,kind,parent_id,formed_on:'2000-01-01'})).unit_id;
  const root=await make('Батальйон','battalion'),company=await make('1 рота','company',root),child=await make('1 взвод','platoon',company),other=await make('2 рота','company',root);
  const url=id=>base+`/admin/organization/staff?unit_id=${id}&on=2026-01-01`;
  await page.goto(url(company));await page.locator('[data-map-panel] > summary').click();
  const mapping=form('[data-map-structure]');await mapping.locator('[name=structure_id]').selectOption('1');await mapping.locator('[name=unit_id]').selectOption(String(root));await submit(mapping,'/map-structure',{reload:true});
  await page.locator('[data-map-panel] > summary').click();
  const positions=form('[data-map-positions]');for(const [id,unit] of [[1,company],[2,child],[3,other]]){const row=positions.locator(`tr[data-id="${id}"]`);await row.locator('[data-map-pick]').check();await row.locator('[data-map-unit]').selectOption(String(unit));}
  await positions.locator('tr[data-id="1"] [data-map-managed]').selectOption(String(child));await submit(positions,'/map-positions',{reload:true});
  let data=await(await context.request.get(url(company),{headers:{Accept:'application/json'}})).json();assert.equal(data.positions.length,2);assert.equal(data.positions.find(p=>p.id===1).managed_unit_id,child);
  console.log('PASS organization staffing: explicit legacy structure/position mapping and leadership links use real IDs');

  await upload([[['1 рота'],40,'Радист'],[['1 рота'],10,'Уточнений командир']],'add');
  assert.equal(await page.locator('[data-excel-row="4"]').isDisabled(),true);await submit(confirm,'/confirm');await page.locator('[data-staff-message]:visible').waitFor();const added=await receipt();
  page.once('dialog',dialog=>dialog.accept('Звірено з офіційною штаткою'));
  await page.locator('[data-preview-rows] tr').nth(1).getByRole('button',{name:'Явно виправити реквізити'}).click();
  await page.locator('[data-preview-rows] tr').nth(1).getByText('accepted',{exact:true}).waitFor();
  data=await(await context.request.get(url(company),{headers:{Accept:'application/json'}})).json();assert.equal(data.positions.length,3);assert.equal(data.positions.find(p=>p.id===1).values.name_short,'уточнений командир');
  const replay=await context.request.post(base+`/admin/organization/staff/imports/${added}/confirm`,{data:{selected_rows:[3]}});assert.equal(replay.status(),200);
  console.log('PASS organization staffing: partial confirmation, persisted conflicts, explicit correction and repeated confirmation keep positions unique');

  await page.goto(url(child));await upload([[['1 взвод'],20,'Оператор']],'official','Ротна версія');const before=await preview.evaluate(n=>[...new FormData(n)].filter(([key])=>key!=='file'));
  const blocked=await submit(confirm,'/confirm');assert.equal(blocked.status(),409);await page.locator('[data-staff-error]').getByText(/Спочатку явно завершіть/).waitFor();assert.deepEqual(await preview.evaluate(n=>[...new FormData(n)].filter(([key])=>key!=='file')),before);assert.equal(await page.locator('[data-preview-panel]').isVisible(),true);
  const history=await context.request.get(base+'/staff/history?version_id=1'),html=await history.text(),records=JSON.parse(html.match(/<script id="history-records"[^>]*>([\s\S]*?)<\/script>/)[1]);
  for(const r of Object.values(records)){const response=await context.request.post(base+`/staff/assignments/${r.id}/correct`,{headers:{Accept:'application/json'},form:{revision:r.revision,person_id:r.person_id,position_id:r.staff_position_id,assigned_from:r.assigned_from,assigned_to:'2025-12-31',release_order_number:'К-1',release_order_date:'2025-12-31',completion_reason:'other'}});assert.equal(response.status(),200,await response.text());}
  const saved=await submit(confirm,'/confirm');assert.equal(saved.status(),200,await saved.text());
  data=await(await context.request.get(url(company),{headers:{Accept:'application/json'}})).json();assert.deepEqual(data.positions.map(p=>p.number),[10,20,40]);assert.ok(data.positions.every(p=>![1,2,3].includes(p.id)));
  const newPosition=data.positions.find(p=>p.number===20),newVersion=newPosition.version_id;assert.equal(data.versions.find(v=>v.id===1).valid_to,null);
  const roster=await context.request.get(base+'/person-positions?as_of=2026-01-01');assert.equal(roster.status(),200);assert.match(await roster.text(),/Сукупний чинний штат/);
  console.log('PASS organization staffing: unfinished assignments block official import without resetting drafts; explicit completion enables a vacant company snapshot');

  let response=await context.request.post(base+'/staff/assignments/create',{headers:{Accept:'application/json'},form:{position_id:newPosition.id,person_id:3,assigned_from:'2026-01-02',assignment_order_number:'21',assignment_order_date:'2026-01-01'}});assert.equal(response.status(),200,await response.text());
  await page.goto(url(child));await upload([[['1 взвод'],20,'Правильна посада']],'replace');await confirm.locator('[name=reason]').fill('Помилковий примірник штатки');await confirm.locator('details > summary').click();await page.locator(`[data-remove-position="${newPosition.id}"]`).check();await confirm.locator('[name=confirm_removal]').check();response=await submit(confirm,'/confirm');assert.equal(response.status(),200,await response.text());const replaced=await receipt();
  await page.reload();const queue=page.locator('[data-reassignment-list] details');assert.equal(await queue.count(),1);assert.match(await queue.innerText(),/Гамма Тест/);await queue.locator(':scope > summary').click();const reassignment=queue.locator('form');assert.equal(await date(reassignment,'assigned_from').inputValue(),'02.01.2026');assert.equal(await reassignment.locator('[name=order_number]').inputValue(),'21');await reassignment.locator('[name=confirmed]').check();response=await submit(reassignment,'/reassign/');assert.equal(response.status(),200,await response.text());await queue.waitFor({state:'detached'});
  await page.goto(base+'/staff/history?version_id='+newVersion);for(const id of [newPosition.id, ...(await page.locator('[data-position-id]').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.positionId))))]){const position=page.locator(`[data-position-id="${id}"]`);if(await position.count()&&!await position.evaluate(n=>n.open))await position.locator(':scope > summary').click();}assert.match(await page.locator('body').innerText(),/Анульовані/);assert.match(await page.locator('body').innerText(),/02.01.2026/);
  await page.goto(url(child));const withdraw=form('[data-withdraw]');await withdraw.locator('..').locator(':scope > summary').click();await withdraw.locator('[name=receipt_id]').fill(String(replaced));await withdraw.locator('[name=reason]').fill('Контрольована перевірка залежностей');await withdraw.locator('[name=confirmed]').check();response=await submit(withdraw,'/withdraw');assert.equal(response.status(),409);assert.equal(await withdraw.locator('[name=reason]').inputValue(),'Контрольована перевірка залежностей');assert.match(await page.locator('[data-staff-error]').innerText(),/подальші призначення/);
  await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(errors,[]);
  console.log('PASS organization staffing: controlled replacement queues actual dates/orders, reassignment keeps history, dependent withdrawal is refused and mobile layout fits');
 }finally{await page.close();}
};

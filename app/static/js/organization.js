/* Organization sorting, dated reparenting and staffing bindings remain distinct actions. */
(() => {
 'use strict';
 const root=document.querySelector('[data-organization]');if(!root)return;
 let tree=JSON.parse(root.querySelector('[data-org-data]').textContent),selected=Number(root.dataset.selectedUnit)||null,dragged=null,selectionRequest=0,attachParentFor=null;
 const expanded=new Set(),forms=[...root.querySelectorAll('[data-org-form]')],message=root.querySelector('[data-org-message]');
 const names={unit:'Військова частина',regiment:'Полк',battalion:'Батальйон',company:'Рота',platoon:'Взвод',squad:'Відділення',other:'Інший підрозділ'};
 const operations={create:'Створено',state:'Назва / основне підпорядкування',dissolve:'Розформовано',annul:'Анульовано',order:'Порядок відображення',operational:'Оперативне підпорядкування',coverage:'Джерело штатки',map:'Явне зіставлення',import:'Імпорт штатки',withdraw:'Відкликання імпорту',position:'Виправлення посади',position_annul:'Анулювання посади',reassignment:'Повторне призначення'};
 const allNodes=()=>new Map([...tree.units,...(tree.inactive_units||[])].map(unit=>[unit.id,unit]));
 const label=id=>id===null||id===undefined?'Без батьківського':`${allNodes().get(id)?.name||'Підрозділ'} · ID ${id}`;
 const display=value=>window.ProfileDates?.format(value)||value||'по цей час';
 function notify(text,danger=false){message.hidden=false;message.className='alert '+(danger?'alert-danger':'alert-info');message.textContent=text;}
 async function request(path,body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let result;try{result=await response.json();}catch{throw Error('Не вдалося прочитати відповідь сервера. Введені дані збережені.');}
  if(!response.ok){const error=Error(typeof result.detail==='string'?result.detail:'Операцію відхилено.');error.field=result.field;throw error;}return result;
 }
 function urlSelection(){const url=new URL(location.href);url.searchParams.set('on',tree.on);if(selected)url.searchParams.set('unit_id',selected);else url.searchParams.delete('unit_id');history.replaceState({},'',url);root.querySelector('form[method=get] [name=unit_id]').value=selected||'';}
 function button(text,handler,extra=''){const node=document.createElement('button');node.type='button';node.className='btn btn-sm btn-link '+extra;node.textContent=text;node.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();handler(event);});return node;}
 function parentOptions(){
  for(const field of root.querySelectorAll('[data-org-parent-options]')){
   const previous=field.value;field.replaceChildren(new Option(field.hasAttribute('data-required-parent')?'Виберіть підрозділ':'Без батьківського',''));
   for(const unit of tree.units){if(field.closest('[data-org-selected]')&&unit.id===selected)continue;field.add(new Option(`${unit.name} · ID ${unit.id}`,unit.id));}
   if([...field.options].some(option=>option.value===previous))field.value=previous;
  }
 }
 function renderTree(){
  const holder=root.querySelector('[data-org-tree]');holder.replaceChildren();const list=document.createElement('ul');list.className='org-tree';list.dataset.orgParent='';holder.append(list);
  const nodes=new Map(tree.units.map(unit=>[unit.id,unit])),elements=new Map();
  for(const unit of tree.units){
   const item=document.createElement('li');item.className='org-node'+(unit.id===selected?' selected':'');item.dataset.orgUnit=unit.id;item.dataset.orgParent=unit.parent_id??'';
   const details=document.createElement('details');details.open=expanded.has(unit.id);details.addEventListener('toggle',()=>details.open?expanded.add(unit.id):expanded.delete(unit.id));
   const summary=document.createElement('summary'),handle=document.createElement('span');handle.textContent='⠿';handle.draggable=true;handle.dataset.orgDrag=unit.id;handle.title='Змінити порядок серед дітей одного батька';handle.setAttribute('aria-label',handle.title);
   handle.addEventListener('dragstart',event=>{dragged=unit.id;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',String(unit.id));event.stopPropagation();});handle.addEventListener('dragend',()=>{dragged=null;root.querySelectorAll('.drag-target').forEach(node=>node.classList.remove('drag-target'));});
   const select=button(unit.name,()=>selectUnit(unit.id));select.dataset.orgSelect=unit.id;
   const meta=document.createElement('span');meta.className='org-unit-meta';meta.textContent=`${names[unit.kind]||unit.kind} · ${unit.id}`;
   summary.append(handle,select,meta,button('↑',()=>move(unit.id,-1),'org-sort-button'),button('↓',()=>move(unit.id,1),'org-sort-button'));details.append(summary);
   const children=document.createElement('ul');children.dataset.orgParent=unit.id;details.append(children);item.append(details);elements.set(unit.id,{item,children});
   summary.addEventListener('dragover',event=>{if(dragged!==null&&dragged!==unit.id&&nodes.get(dragged)?.parent_id===unit.parent_id){event.preventDefault();event.dataTransfer.dropEffect='move';item.classList.add('drag-target');}});
   summary.addEventListener('dragleave',()=>item.classList.remove('drag-target'));
   summary.addEventListener('drop',async event=>{event.preventDefault();event.stopPropagation();item.classList.remove('drag-target');const source=nodes.get(dragged);if(!source||source.id===unit.id)return;if(source.parent_id!==unit.parent_id){notify('Зміну батьківського підрозділу виконайте окремою формою основного підпорядкування.',true);return;}const siblings=tree.units.filter(node=>node.parent_id===unit.parent_id).map(node=>node.id),next=siblings.filter(id=>id!==source.id);let index=next.indexOf(unit.id);if(event.clientY>summary.getBoundingClientRect().top+summary.getBoundingClientRect().height/2)index+=1;next.splice(index,0,source.id);await sort(unit.parent_id,next);});
  }
  // Iterative attachment supports arbitrary hierarchy depth without recursive rendering.
  for(const unit of tree.units){const target=unit.parent_id===null?list:elements.get(unit.parent_id)?.children;if(target)target.append(elements.get(unit.id).item);}
  root.querySelector('[data-org-empty]').hidden=tree.units.length>0;
  if(tree.inactive_units?.length){const archive=document.createElement('details');archive.className='org-operation';const summary=document.createElement('summary');summary.textContent='Неактивні / анульовані підрозділи';archive.append(summary);for(const unit of tree.inactive_units){const row=document.createElement('div');row.append(button(`${unit.name} · ID ${unit.id} · ${unit.annulled_at?'анульований':unit.dissolved_on?'розформований':'ще не сформований'}`,()=>selectUnit(unit.id)));archive.append(row);}holder.append(archive);}
  parentOptions();
 }
 async function refresh(){tree=await request('/admin/organization/tree?on='+encodeURIComponent(tree.on));renderTree();urlSelection();if(selected)await selectUnit(selected);}
 async function sort(parent,ids){
  const nodes=allNodes(),revisions=Object.fromEntries(ids.map(id=>[id,nodes.get(id).revision]));
  try{const result=await request('/admin/organization/reorder',{on:tree.on,parent_id:parent,ids,revisions});notify(result.message);await refresh();}catch(error){notify(error.message,true);}
 }
 async function move(id,delta){const node=allNodes().get(id),ids=tree.units.filter(unit=>unit.parent_id===node.parent_id).map(unit=>unit.id),index=ids.indexOf(id),other=index+delta;if(other<0||other>=ids.length)return;[ids[index],ids[other]]=[ids[other],ids[index]];await sort(node.parent_id,ids);}
 function historyTable(title,headers,rows){const section=document.createElement('section');section.className='mb-3';const heading=document.createElement('h3');heading.className='h6';heading.textContent=title;section.append(heading);if(!rows.length){section.append('Записів немає.');return section;}const wrap=document.createElement('div');wrap.className='table-responsive';const table=document.createElement('table');table.className='table table-sm';const head=document.createElement('tr');for(const name of headers){const cell=document.createElement('th');cell.textContent=name;head.append(cell);}const thead=document.createElement('thead');thead.append(head);table.append(thead);const body=document.createElement('tbody');for(const values of rows){const row=document.createElement('tr');for(const value of values){const cell=document.createElement('td');if(value instanceof Node)cell.append(value);else cell.textContent=value??'—';row.append(cell);}body.append(row);}table.append(body);wrap.append(table);section.append(wrap);return section;}
 function renderHistory(data){
  const history=root.querySelector('[data-org-history]');history.replaceChildren();
  history.append(historyTable('Назви та основне підпорядкування',['Період','Назва','Основний батьківський'],data.states.map(row=>[`${display(row.valid_from)} — ${display(row.valid_to)}`,row.name,label(row.primary_parent_id)])));
  history.append(historyTable('Оперативне підпорядкування',['Період','Оперативний батьківський','Примітка','Дія'],data.operational.map(row=>{
   let action='—';if(!data.unit.annulled_at){const form=document.createElement('form');form.className='d-flex flex-wrap gap-1';const end=document.createElement('input');end.type='date';end.name='valid_to';end.value=row.valid_to||tree.on;end.className='form-control form-control-sm';end.required=true;end.setAttribute('aria-label','Завершення оперативного підпорядкування');const save=document.createElement('button');save.className='btn btn-sm btn-outline-secondary';save.textContent='Завершити';const error=document.createElement('p');error.className='text-danger';form.append(end,save,error);form.addEventListener('submit',async event=>{event.preventDefault();if(!form.reportValidity())return;try{save.disabled=true;await request(`/admin/organization/operational/${row.id}/close`,{revision:row.revision,valid_to:end.value});notify('Період оперативного підпорядкування завершено.');await refresh();}catch(e){error.textContent=e.message;}finally{save.disabled=false;}});action=form;}
   return [`${display(row.valid_from)} — ${display(row.valid_to)}`,label(row.parent_id),row.note,action];
  })));
  history.append(historyTable('Журнал операцій',['Час UTC','Автор ID','Операція','Причина'],data.audit.map(row=>[row.occurred_at,row.actor_user_id,operations[row.operation]||row.operation,row.reason])));
  window.ProfileDates?.enhance(history);
 }
 async function selectUnit(id){
  selected=id;urlSelection();root.querySelectorAll('[data-org-unit]').forEach(node=>node.classList.toggle('selected',Number(node.dataset.orgUnit)===id));const serial=++selectionRequest;
  try{
   const data=await request(`/admin/organization/units/${id}`);if(serial!==selectionRequest)return;
   const unit=data.unit,current=tree.units.find(node=>node.id===id),state=data.states.find(row=>row.valid_from<=tree.on&&(!row.valid_to||row.valid_to>=tree.on))||data.states.at(-1);
   root.querySelector('[data-org-select-hint]').hidden=true;root.querySelector('[data-org-selected]').hidden=false;root.querySelector('[data-org-title]').textContent=current?.name||state?.name||'Підрозділ';root.querySelector('[data-org-unit-id]').textContent='ID '+id;
   root.querySelector('[data-org-status]').textContent=unit.annulled_at?'Анульовано: '+(unit.annulment_reason||''):unit.dissolved_on?'Розформовано, останній день '+display(unit.dissolved_on):names[unit.kind]||unit.kind;
   parentOptions();for(const form of forms){if(form.dataset.orgForm==='create')continue;form.elements.revision.value=unit.revision;form.querySelectorAll('input,select,textarea,button').forEach(field=>field.disabled=Boolean(unit.annulled_at));}
   root.querySelector('[data-org-form=name] [name=name]').value=state?.name||'';root.querySelector('[data-org-form=parent] [name=parent_id]').value=current?.parent_id??state?.primary_parent_id??'';
   root.querySelector('[data-org-create-child]').disabled=Boolean(unit.annulled_at);root.querySelector('[data-org-create-parent]').disabled=Boolean(unit.annulled_at);
   const staff=root.querySelector('[data-org-staff-link]');staff.href='/admin/organization/staff?unit_id='+id+'&on='+encodeURIComponent(tree.on);
   renderHistory(data);root.dispatchEvent(new CustomEvent('organization:selected',{bubbles:true,detail:{unit:{...unit,name:state?.name},tree,on:tree.on,history:data}}));
  }catch(error){notify(error.message,true);}
 }
 for(const form of forms){
  form.addEventListener('input',()=>{form.querySelectorAll('.is-invalid').forEach(node=>node.classList.remove('is-invalid'));});
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(form.dataset.pending==='1'||!form.reportValidity())return;const errorBox=form.querySelector('[data-org-error]'),button=form.querySelector('button[type=submit],button:not([type])');errorBox.hidden=true;form.dataset.pending='1';button.disabled=true;
   try{
    const body=Object.fromEntries(new FormData(form));if('confirmed' in body)body.confirmed=form.elements.confirmed.checked;if(body.revision)body.revision=Number(body.revision);
    const action=form.dataset.orgForm,path=action==='create'?'/admin/organization/units':`/admin/organization/units/${selected}/${action}`;if(action!=='create'&&!selected)throw Error('Спочатку виберіть підрозділ.');
    const result=await request(path,body);notify(result.message);const attach=attachParentFor;if(action==='create'){selected=result.unit_id;form.reset();form.closest('details').open=false;attachParentFor=null;}
    await refresh();
    if(attach){await selectUnit(attach);const parentForm=root.querySelector('[data-org-form=parent]');parentForm.elements.parent_id.value=result.unit_id;parentForm.closest('details').open=true;notify('Батьківський підрозділ створено. Окремо збережіть основне підпорядкування дитини з фактичної дати.');}
   }catch(error){errorBox.textContent=error.message;errorBox.hidden=false;const field=error.field&&form.elements[error.field];if(field){field.classList.add('is-invalid');form.querySelector(`[data-exact-date-for="${field.name}"]`)?.classList.add('is-invalid');field.focus();}else{errorBox.tabIndex=-1;errorBox.focus();}}
   finally{form.dataset.pending='0';button.disabled=Boolean(form.closest('[data-org-selected]')&&allNodes().get(selected)?.annulled_at);}
  });
 }
 root.querySelector('[data-org-create-child]').addEventListener('click',()=>{attachParentFor=null;const panel=root.querySelector('[data-org-create-panel]');panel.open=true;panel.querySelector('[name=parent_id]').value=selected||'';panel.querySelector('[name=name]').focus();});
 root.querySelector('[data-org-create-parent]').addEventListener('click',()=>{attachParentFor=selected;const panel=root.querySelector('[data-org-create-panel]');panel.open=true;panel.querySelector('[name=parent_id]').value='';panel.querySelector('[name=name]').focus();notify('Створіть новий батьківський підрозділ, потім окремо підтвердьте основне підпорядкування вибраної дитини.');});
 root.querySelector('[data-org-expand]').addEventListener('click',()=>root.querySelectorAll('[data-org-unit]>details').forEach(node=>node.open=true));root.querySelector('[data-org-collapse]').addEventListener('click',()=>root.querySelectorAll('[data-org-unit]>details').forEach(node=>node.open=false));
 window.ProfileDates?.enhance(root);renderTree();if(selected)selectUnit(selected);
})();

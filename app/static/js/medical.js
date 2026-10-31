/* Protected subject editors reuse personal sessions, document uploads and files. */
(() => {
 'use strict';
 const panels=[...document.querySelectorAll('[data-medical-panel]')];if(!panels.length)return;
 const meta=JSON.parse(document.getElementById('medical-ui-metadata').textContent),pid=panels[0].dataset.personId,base=`/persons/${pid}/medical`;
 let csrf='',role='',state=null;
 const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 async function request(url,body){const multipart=body instanceof FormData;const response=await fetch(url,{method:body===undefined?'GET':'POST',cache:'no-store',headers:body===undefined?{}:{'X-CSRF-Token':csrf,...(multipart?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:multipart?body:JSON.stringify(body)});let data;try{data=await response.json();}catch{throw Error('Сервер недоступний. Введені значення збережено.');}if(!response.ok)throw Error(data.detail||'Не вдалося зберегти.');return data;}
 function message(panel,text,error=false){const n=panel.querySelector('[data-medical-message]');n.textContent=text;n.className=text?'alert '+(error?'alert-danger':'alert-success'):'';}
 function button(text,fn){const n=el('button',text,'btn btn-sm btn-outline-secondary me-2 my-1');n.type='button';n.addEventListener('click',async()=>{n.disabled=true;try{await fn();}catch(e){message(n.closest('[data-medical-panel]'),e.message,true);}finally{n.disabled=false;}});return n;}
 function edit(panel,record){const form=panel.querySelector('[data-medical-form]');form.reset();form.dataset.key=record?.id||'';form.dataset.revision=record?.revision||'';
  for(const field of meta.fields[panel.dataset.medicalPanel]){const input=form.elements[field[0]];if(input.type==='checkbox')input.checked=!!record?.[field[0]];else if(record)input.value=record[field[0]]??'';}
  panel.querySelector('[data-medical-editor]').open=true;form.querySelector('input,select')?.focus();
 }
 function related(card,kind,id){if(!id)return;const a=el('a',`${meta.labels[kind]} №${id} `);a.href='#'+kind;a.addEventListener('click',()=>{const p=panels.find(p=>p.dataset.medicalPanel===kind);const row=state[kind].find(r=>r.id===id);if(row)edit(p,row);});card.append(a);}
 function documentUI(panel,card,kind,row){if(!meta.documents[kind])return;
  const details=el('details'),summary=el('summary','Документи та копії');details.append(summary);card.append(details);
  const fk={exams:'exam_id',injuries:'injury_id',awards:'award_id'}[kind];
  for(const link of state.links.filter(link=>link[fk]===row.id)){
   const block=el('div',undefined,'border-start ps-2 mb-2');block.append(el('p',`${meta.documents[kind][link.category]} · документ №${link.document_id}`));details.append(block);
   for(const file of link.files){const a=el('a',file.name,'me-2');a.href=`/persons/${pid}/documents/files/${file.id}`;block.append(a);
    if(role!=='viewer')block.append(button('Вилучити копію',async()=>{const reason=prompt('Причина вилучення копії');if(!reason)return;await request(`/persons/${pid}/documents/files/${file.id}/remove`,{revision:file.revision,reason});await load();message(panel,'Копію вилучено з поточного перегляду; історію збережено.');}));
   }
   if(role!=='viewer'){
    const upload=el('form'),file=el('input');file.type='file';file.accept='.jpg,.jpeg,.png,.pdf';file.required=true;file.name='file';upload.append(file);
    const submit=el('button','Додати копію','btn btn-sm btn-outline-primary');upload.append(submit);block.append(upload);
    upload.addEventListener('submit',async e=>{e.preventDefault();submit.disabled=true;try{const data=new FormData(upload);data.set('revision',link.document_revision);data.set('side','page');await request(`/persons/${pid}/documents/${link.document_id}/files`,data);await load();message(panel,'Копію збережено.');}catch(error){message(panel,error.message,true);}finally{submit.disabled=false;}});
   }
  }
  if(role==='viewer')return;
  const form=el('form'),category=el('select',undefined,'form-select my-1');category.name='category';
  for(const [value,label] of Object.entries(meta.documents[kind])){const option=el('option',label);option.value=value;category.append(option);}form.append(category);
  const documentID=el('input');documentID.type='number';documentID.min='1';documentID.placeholder='ID наявного документа (або порожньо)';documentID.setAttribute('aria-label','ID наявного документа');form.append(documentID);
  const submit=el('button','Додати документ','btn btn-sm btn-outline-primary');form.append(submit);details.append(form);
  form.addEventListener('submit',async e=>{e.preventDefault();submit.disabled=true;try{await request(`${base}/${kind}/${row.id}/documents`,{category:category.value,revision:row.revision,document_id:documentID.value?Number(documentID.value):null});await load();message(panel,'Документ прив’язано. Відкрийте його блок, щоб додати копії.');}catch(error){message(panel,error.message,true);}finally{submit.disabled=false;}});
 }
 function render(){for(const panel of panels){const kind=panel.dataset.medicalPanel;panel.querySelector('[data-medical-login]').hidden=true;panel.querySelector('[data-medical-content]').hidden=false;
  panel.querySelector('[data-medical-editor]').hidden=role==='viewer';
  panel.querySelectorAll('[data-injury-choice]').forEach(select=>{const current=select.value;select.replaceChildren(new Option('Не зазначено',''),...state.injuries.map(r=>new Option(`№${r.id} · ${r.occurred_on||'Дата невідома'} · ${r.description||''}`,r.id)));select.value=current;});
  const list=panel.querySelector('[data-medical-list]');const expanded=new Set([...list.querySelectorAll('[data-medical-record]')].filter(card=>card.querySelector('details')?.open).map(card=>card.dataset.medicalRecord));list.replaceChildren();
  for(const row of state[kind]){const card=el('article',undefined,'border rounded p-2 mb-2');card.dataset.medicalRecord=row.id;card.append(el('h3',`Запис №${row.id}`,'h6'));
   for(const [key,label,type,options] of meta.fields[kind]){const raw=row[key];if(raw!==null&&raw!==undefined&&raw!=='')card.append(el('p',`${label}: ${type==='select'?options[raw]||raw:type==='checkbox'?(raw?'Так':'Ні'):raw}`,'mb-1 text-break'));}
   if(role!=='viewer')card.append(button('Редагувати',()=>edit(panel,row)));
   if(kind==='exams'&&row.status==='COMPLETED'&&role!=='viewer')card.append(button('Зробити активним',async()=>{await request(base+'/active',{exam_id:row.id,revision:state.selection.revision});await load();message(panel,'Ручний вибір активного ВЛК збережено.');window.refreshProfileOverview?.();}));
   related(card,'injuries',row.injury_id);related(card,'awards',row.award_id);
   if(kind==='injuries')for(const target of ['exams','awards','tasks'])for(const r of state[target].filter(r=>r.injury_id===row.id))related(card,target,r.id);
   documentUI(panel,card,kind,row);if(expanded.has(String(row.id))&&card.querySelector('details'))card.querySelector('details').open=true;list.append(card);
  }
  if(!state[kind].length)list.append(el('p','Записів немає.'));
  if(kind==='exams'){panel.querySelector('[data-active-exam]').textContent=state.active_warning||(state.active_exam?`Активне ВЛК №${state.active_exam.id}: ${meta.fitness[state.active_exam.fitness]||'Придатність не зазначена'} (${state.selection.exam_id?'ручний вибір':'автоматично'})`:'Активного завершеного ВЛК немає.');panel.querySelector('[data-exam-auto]').hidden=role==='viewer';}
  if(kind==='tasks'){const pending=panel.querySelector('[data-pending-exams]');pending.replaceChildren(el('h3',`Непройдені ВЛК: ${state.pending_exams.length}`,'h6'));for(const r of state.pending_exams)related(pending,'exams',r.id);for(const warning of state.warnings)pending.append(el('p',warning,'text-warning'));
   const audit=panel.querySelector('[data-medical-audit]');audit.replaceChildren(...state.audit.map(r=>el('p',`${r.occurred_at} · користувач №${r.actor_id} · ${r.entity} №${r.entity_id} · ${r.operation} · ${JSON.stringify(r.changes)}`,'small text-break')));
  }
 }}
 async function load(){state=await request(base);render();}
 for(const panel of panels){
  panel.querySelector('[data-medical-auth]').addEventListener('submit',async event=>{event.preventDefault();const form=event.target;try{const result=await request('/auth/login',{username:form.username.value,password:form.password.value});csrf=result.csrf_token;form.password.value='';const me=await request('/auth/me');role=me.role;await load();message(panel,'Вхід виконано.');}catch(error){message(panel,error.message,true);}});
  panel.querySelector('[data-medical-new]').addEventListener('click',()=>edit(panel,null));
  panel.querySelector('[data-exam-auto]')?.addEventListener('click',async()=>{try{await request(base+'/active',{exam_id:null,revision:state.selection.revision});await load();message(panel,'Увімкнено автоматичний вибір.');window.refreshProfileOverview?.();}catch(error){message(panel,error.message,true);}});
  panel.querySelector('[data-medical-form]').addEventListener('submit',async event=>{event.preventDefault();const form=event.target,submit=form.querySelector('[type=submit],button:not([type])');submit.disabled=true;message(panel,'');
   try{const fields={};for(const [key,,type] of meta.fields[panel.dataset.medicalPanel])fields[key]=type==='checkbox'?form.elements[key].checked:form.elements[key].value;
    const result=await request(base+'/'+panel.dataset.medicalPanel+(form.dataset.key?'/'+form.dataset.key:''),{fields,revision:form.dataset.revision||null});await load();edit(panel,state[panel.dataset.medicalPanel].find(r=>r.id===result.id));message(panel,'Збережено. '+(result.warnings||[]).join(' '));window.refreshProfileOverview?.();
   }catch(error){message(panel,error.message,true);form.querySelector('input,select')?.focus();}finally{submit.disabled=false;}
  });
 }
 request('/auth/me').then(async me=>{csrf=me.csrf_token;role=me.role;panels.forEach(panel=>panel.querySelector('[data-dev-auth-warning]').hidden=!me.dev_auth_bypass);await load();}).catch(error=>{panels.forEach(panel=>{panel.querySelector('[data-medical-login]').hidden=false;message(panel,error.message,true);});});
})();

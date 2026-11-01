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
 function configureExam(panel){
  if(panel.dataset.medicalPanel!=='exams')return;
  const form=panel.querySelector('[data-medical-form]'),status=form.elements.status.value,previous=form.dataset.originalStatus;
  const allowed=['status','basis','basis_note','injury_id','planned_on','basis_document_id',...(status==='COMPLETED'?['ended_on','issued_on','number','fitness','institution','diagnosis']:status==='INTERRUPTED'?['interrupted_on','interruption_reason']:[])];
  panel.querySelectorAll('[data-medical-field]').forEach(n=>{n.hidden=!allowed.includes(n.dataset.medicalField);n.querySelectorAll('input,select,textarea,button').forEach(input=>input.disabled=n.hidden);});
  for(const option of form.elements.status.options)option.disabled=option.value==='INTERRUPTED'? !['PLANNED','INTERRUPTED'].includes(previous):previous==='INTERRUPTED';
  for(const key of ['planned_on','issued_on','number','fitness','interrupted_on','interruption_reason'])form.elements[key].required=(status==='PLANNED'&&key==='planned_on')||(status==='COMPLETED'&&['issued_on','number','fitness'].includes(key))||(status==='INTERRUPTED'&&['planned_on','interrupted_on','interruption_reason'].includes(key));
 }
 function edit(panel,record){const form=panel.querySelector('[data-medical-form]');ProfileUI.resetForm(form);form.dataset.key=record?.id||'';form.dataset.revision=record?.revision||'';form.dataset.originalStatus=record?.status||'';
  for(const field of meta.fields[panel.dataset.medicalPanel]){const input=form.elements[field[0]];if(input.type==='checkbox')input.checked=!!record?.[field[0]];else if(record)input.value=record[field[0]]??'';}
  for(const input of form.elements)input.disabled=false;
  if(['injury_vlk','exam_vlk'].includes(record?.kind))for(const key of ['injury_id','award_id','status','decision_reason'])form.elements[key].disabled=true;
  configureExam(panel);ProfileUI.openEditor(panel.querySelector('[data-medical-editor]'));form.querySelector('input,select')?.focus();
 }
 function related(card,kind,id){if(!id)return;const a=el('a',`${meta.labels[kind]} №${id} `);a.href='#'+kind;a.addEventListener('click',()=>{const target=panels.find(p=>p.dataset.medicalPanel===kind);const row=state[kind].find(r=>r.id===id);if(!row)return;if(kind==='tasks'&&row.status!=='OPEN'){target.querySelector('[data-task-history]').checked=true;render();}const details=target.querySelector(`[data-medical-record="${id}"] [data-record-card]`);if(details)details.open=true;});card.append(a);}
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
  if(role==='viewer')ProfileUI.closeEditor(panel.querySelector('[data-medical-editor]'));panel.querySelector('[data-medical-new]').hidden=role==='viewer';
  panel.querySelectorAll('[data-injury-choice]').forEach(select=>{const current=select.value;select.replaceChildren(new Option('Не зазначено',''),...state.injuries.map(r=>new Option(`№${r.id} · ${ProfileDates.format(r.occurred_on)||'Дата невідома'} · ${r.description||''}`,r.id)));select.value=current;});
  const list=panel.querySelector('[data-medical-list]');const expanded=new Set([...list.querySelectorAll('[data-medical-record]')].filter(card=>card.querySelector('[data-record-card]')?.open).map(card=>card.dataset.medicalRecord));const documentsExpanded=new Set([...list.querySelectorAll('[data-medical-record]')].filter(card=>card.querySelector('[data-record-card] > details')?.open).map(card=>card.dataset.medicalRecord));list.replaceChildren();
  for(const row of state[kind]){if(kind==='tasks'&&row.status!=='OPEN'&&!panel.querySelector('[data-task-history]').checked)continue;const article=el('article',undefined,'border rounded p-2 mb-2');article.dataset.medicalRecord=row.id;let card=article;
   if(kind==='tasks')article.dataset.taskKind=row.kind;
   card=el('details');card.dataset.recordCard='';article.append(card);
   if(kind==='exams'){
    card.dataset.examCard='';
    const summary=el('summary',`Запис №${row.id} · ${meta.fields.exams.find(f=>f[0]==='status')[3][row.status]} · Початок: ${ProfileDates.format(row.planned_on)||'—'} · Завершення: ${ProfileDates.format(row.ended_on)||'—'}${row.status==='INTERRUPTED'?' · Переривання: '+(ProfileDates.format(row.interrupted_on)||'—'):''} · Довідка: ${row.number||'—'} · ${meta.fitness[row.fitness]||'—'}${row.is_current?' · Актуальне ВЛК':''}`);
    summary.className='profile-record-summary';card.append(summary);
   }else{
    const label=kind==='injuries'?`${ProfileDates.format(row.occurred_on)||'—'} · ${row.description||'Поранення'} · ${row.vlk_stage_label||''}`:kind==='awards'?`${row.name||'Нагородження'} · ${meta.fields.awards.find(f=>f[0]==='status')[3][row.status]}`:kind==='dna'?`${row.envelope_number||'—'} · ${ProfileDates.format(row.collected_on)||'—'} · ${row.storage_unit||'—'}`:`${row.title} · ${row.stage_label||meta.fields.tasks.find(f=>f[0]==='status')[3][row.status]}`;
    card.append(el('summary',`Запис №${row.id} · ${label}`,'profile-record-summary'));
   }
   for(const [key,label,type,options] of meta.fields[kind]){const raw=row[key];if(raw!==null&&raw!==undefined&&raw!=='')card.append(el('p',`${label}: ${type==='select'?options[raw]||raw:type==='date'?ProfileDates.format(raw):type==='checkbox'?(raw?'Так':'Ні'):raw}`,'mb-1 text-break'));}
   if(row.vlk_stage_label)card.append(el('p',row.vlk_stage_label,'fw-semibold'));
   if(['injury_vlk','exam_vlk'].includes(row.kind)){
    card.append(el('p',row.stage_label,'fw-semibold'));
    if(row.stage==='NOT_NEEDED')card.append(el('p',row.decision_reason||'Причина раніше не зазначена.'));
    for(const id of row.exam_ids)related(card,'exams',id);
    if(role!=='viewer'){
     if(row.status==='OPEN'){
      if(row.kind==='injury_vlk')card.append(button('ВЛК не потрібна',async()=>{const reason=prompt('Причина: чому ВЛК не потрібна?');if(reason===null)return;await request(`${base}/tasks/${row.id}/vlk-decision`,{action:'not_needed',reason,revision:row.revision});await load();message(panel,'Рішення щодо ВЛК збережено.');}));
      card.append(button('Відкрити ВЛК',()=>{const target=panels.find(p=>p.dataset.medicalPanel==='exams');edit(target,null);const form=target.querySelector('[data-medical-form]');form.elements.status.value='NEEDS_EXAM';form.elements.basis.value='INJURY';form.elements.injury_id.value=row.injury_id?String(row.injury_id):'';configureExam(target);location.hash='exams';}));
     }else if(row.stage==='NOT_NEEDED')card.append(button('Скасувати рішення «ВЛК не потрібна»',async()=>{const reason=prompt('Причина скасування рішення');if(reason===null)return;await request(`${base}/tasks/${row.id}/vlk-decision`,{action:'reopen',reason,revision:row.revision});await load();message(panel,'Рішення скасовано; стан перераховано за пов’язаними ВЛК.');}));
    }
   }
   if(role!=='viewer')card.append(button('Редагувати',()=>edit(panel,row)));
   if(kind==='exams'&&row.status==='COMPLETED'&&role!=='viewer')card.append(button('Зробити активним',async()=>{await request(base+'/active',{exam_id:row.id,revision:state.selection.revision});await load();message(panel,'Ручний вибір активного ВЛК збережено.');window.refreshProfileOverview?.();}));
   related(card,'injuries',row.injury_id);related(card,'awards',row.award_id);
   if(kind==='injuries')for(const target of ['exams','awards','tasks'])for(const r of state[target].filter(r=>r.injury_id===row.id))related(card,target,r.id);
   documentUI(panel,card,kind,row);if(expanded.has(String(row.id)))card.open=true;if(documentsExpanded.has(String(row.id))&&card.querySelector('details'))card.querySelector('details').open=true;list.append(article);
  }
  if(!list.children.length)list.append(el('p',kind==='tasks'?'Відкритих завдань немає. Для історії увімкніть показ завершених.':'Записів немає.'));
  if(kind==='exams'){panel.querySelector('[data-active-exam]').textContent=state.active_warning||(state.active_exam?`Активне ВЛК №${state.active_exam.id}: ${meta.fitness[state.active_exam.fitness]||'Придатність не зазначена'} (${state.selection.exam_id?'ручний вибір':'автоматично'})`:'Актуальне ВЛК не визначено');panel.querySelector('[data-exam-auto]').hidden=role==='viewer';}
  if(kind==='tasks'){const pending=panel.querySelector('[data-pending-exams]');pending.replaceChildren(el('h3',`Непройдені ВЛК: ${state.pending_exams.length}`,'h6'));for(const r of state.pending_exams)related(pending,'exams',r.id);for(const warning of state.warnings)pending.append(el('p',warning,'text-warning'));
   const audit=panel.querySelector('[data-medical-audit]');audit.replaceChildren(...state.audit.map(r=>el('p',`${r.occurred_at} · користувач №${r.actor_id} · ${r.entity} №${r.entity_id} · ${r.operation} · ${JSON.stringify(ProfileDates.display(r.changes))}`,'small text-break')));
  }
 }}
 async function load(){state=await request(base);render();}
 for(const panel of panels){
  panel.querySelector('[data-task-history]')?.addEventListener('change',render);
  panel.querySelector('[data-medical-auth]').addEventListener('submit',async event=>{event.preventDefault();const form=event.target;try{const result=await request('/auth/login',{username:form.username.value,password:form.password.value});csrf=result.csrf_token;form.password.value='';const me=await request('/auth/me');role=me.role;await load();message(panel,'Вхід виконано.');}catch(error){message(panel,error.message,true);}});
  panel.querySelector('[name=status]')?.addEventListener('change',()=>configureExam(panel));
  configureExam(panel);
  panel.querySelector('[data-medical-new]').addEventListener('click',()=>{message(panel,'');edit(panel,null);});
  panel.querySelector('[data-medical-cancel]').addEventListener('click',()=>{ProfileUI.resetForm(panel.querySelector('[data-medical-form]'));ProfileUI.closeEditor(panel.querySelector('[data-medical-editor]'));message(panel,'');configureExam(panel);});
  panel.querySelector('[data-exam-auto]')?.addEventListener('click',async()=>{try{await request(base+'/active',{exam_id:null,revision:state.selection.revision});await load();message(panel,'Увімкнено автоматичний вибір.');window.refreshProfileOverview?.();}catch(error){message(panel,error.message,true);}});
  panel.querySelector('[data-medical-form]').addEventListener('submit',async event=>{event.preventDefault();const form=event.target,submit=form.querySelector('[type=submit],button:not([type])');submit.disabled=true;message(panel,'');
   try{const fields={};for(const [key,,type] of meta.fields[panel.dataset.medicalPanel])fields[key]=type==='checkbox'?form.elements[key].checked:form.elements[key].value;
    const editing=!!form.dataset.key;if(panel.dataset.medicalPanel==='exams'){if(fields.status!=='COMPLETED')fields.fitness=null;if(fields.status!=='INTERRUPTED'){fields.interrupted_on=null;fields.interruption_reason=null;}}
    const basisDocument=panel.dataset.medicalPanel==='exams'&&form.elements.basis_document_id.value?Number(form.elements.basis_document_id.value):null;
    const result=await request(base+'/'+panel.dataset.medicalPanel+(form.dataset.key?'/'+form.dataset.key:''),{fields,revision:form.dataset.revision||null,basis_document_id:basisDocument});await load();ProfileUI.finishRecord(panel.querySelector('[data-medical-editor]'),form,editing);configureExam(panel);message(panel,(result.warnings||[]).join(' '));window.refreshProfileOverview?.();
   }catch(error){message(panel,error.message,true);form.querySelector('input,select')?.focus();}finally{submit.disabled=false;}
  });
 }
 request('/auth/me').then(async me=>{csrf=me.csrf_token;role=me.role;panels.forEach(panel=>panel.querySelector('[data-dev-auth-warning]').hidden=!(me.open_access||me.dev_auth_bypass));await load();}).catch(error=>{panels.forEach(panel=>{panel.querySelector('[data-medical-login]').hidden=false;message(panel,error.message,true);});});
})();

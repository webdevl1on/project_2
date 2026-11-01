/* Additional profile records share editors/dates/audit, never personnel workflows. */
(() => {
 'use strict';
 const element=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
 for(const panel of document.querySelectorAll('[data-additional-panel]')){
  const kind=panel.dataset.additionalPanel,pid=panel.dataset.personId,url=`/persons/${pid}/profile-records/${kind}`;
  const form=panel.querySelector('form'),editor=panel.querySelector('[data-additional-editor]');
  let data,csrf='',editing=null,pending=false;
  const message=text=>{const node=panel.querySelector('[data-additional-message]');node.textContent=text;node.className=text?'alert alert-danger':'';if(text)node.focus();};
  async function request(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',cache:'no-store',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});let result;try{result=await response.json();}catch{throw Error('Не вдалося отримати відповідь сервера. Введені значення збережено.');}if(!response.ok)throw Error(result.detail||'Не вдалося зберегти запис.');return result;}
  function fields(){const target=panel.querySelector('[data-additional-fields]');if(target.children.length)return;
   for(const [key,label,type,options,required] of data.fields){
    const wrap=element('label',undefined,type==='textarea'?'col-12':'col-md-6'),input=element(type==='select'?'select':type==='textarea'?'textarea':'input',undefined,type==='select'?'form-select':'form-control');wrap.append(element('span',label));
    input.name=key;input.required=required;
    if(type==='select'){input.append(new Option('Оберіть значення',''));for(const [value,title] of Object.entries(options))input.append(new Option(title,value));}
    else {if(type!=='textarea')input.type=type==='geo'?'text':type; if(options)input.maxLength=options;}
    wrap.append(input);target.append(wrap);
    if(type==='geo')suggestions(wrap,input,key);
   }
   ProfileDates.enhance(target);
  }
  function open(row=null){ProfileUI.resetForm(form);editing=row;form.dataset.key=row?.id||'';form.dataset.revision=row?.revision||'';
   for(const [key] of data.fields)form.elements.namedItem(key).value=row?.[key]??'';
   for(const input of form.querySelectorAll('[data-family-geo-id]'))input.value=row?.[input.name]??'';
   form.querySelectorAll('[data-family-suggestions]').forEach(n=>n.replaceChildren());
   ProfileUI.openEditor(editor);message('');
  }
  function suggestions(wrap,input,key){
   const id=element('input');id.type='hidden';id.name=key+'_id';id.dataset.familyGeoId='';wrap.append(id);
   const list=element('div',undefined,'list-group');list.dataset.familySuggestions=key;wrap.append(list);let timer,generation=0;
   input.autocomplete='off';input.addEventListener('input',()=>{id.value='';list.replaceChildren();clearTimeout(timer);const token=++generation,query=input.value.trim();if(query.length<2)return;
    timer=setTimeout(async()=>{try{const result=await request('/geography/search?'+new URLSearchParams({kind:key,q:query}));if(token!==generation||!input.isConnected)return;list.replaceChildren();
     for(const item of result){const button=element('button',`${item.name}${item.context?' · '+item.context:''}`,'list-group-item list-group-item-action');button.type='button';button.addEventListener('click',()=>{generation++;input.value=item.name;id.value=item.id;list.replaceChildren();});list.append(button);}
    }catch{if(token===generation)list.replaceChildren(element('small','Довідник недоступний; ручне введення дозволено.'));}},250);
   });
   form.addEventListener('profile:reset',()=>{generation++;clearTimeout(timer);list.replaceChildren();});
  }
  function summary(row){if(kind==='education')return [data.fields[0][3][row.level_code],row.institution,[ProfileDates.format(row.started_on),ProfileDates.format(row.ended_on)].filter(Boolean).join(' — ')].filter(Boolean).join(' · ');if(kind==='family')return [data.fields[0][3][row.kinship],row.full_name,ProfileDates.format(row.birth_on)].filter(Boolean).join(' · ');if(kind==='directives')return ['Розпорядження'+(row.number?' №'+row.number:''),ProfileDates.format(row.issued_on)].filter(Boolean).join(' · ');return String(row.id);}
  function render(){fields();const list=panel.querySelector('[data-additional-list]'),expanded=new Set([...list.querySelectorAll('[open]')].map(n=>n.dataset.additionalRecord));list.replaceChildren();
   panel.querySelector('[data-additional-new]').hidden=data.role==='viewer';
   for(const row of data.records){const card=element('details',undefined,'profile-record-card border rounded p-2 mb-2');card.dataset.additionalRecord=String(row.id);card.open=expanded.has(String(row.id));card.append(element('summary',summary(row)));
    for(const [key,label,type,options] of data.fields){let value=row[key];if(value===null||value===undefined||value==='')continue;if(type==='date')value=ProfileDates.format(value);if(type==='select')value=options[value]||value;card.append(element('p',`${label}: ${value}`,'mb-1 text-break'));}
    if(kind==='family')card.append(element('p',`Перевірка адреси: ${{matched:'підтверджено довідником',mismatch:'розбіжність із довідником — текст збережено',unknown:'не підтверджено довідником'}[row.validation_status]}`,'small text-secondary'));
    if(data.role!=='viewer'){const button=element('button','Редагувати','btn btn-sm btn-outline-secondary');button.type='button';button.addEventListener('click',()=>open(row));card.append(button);}list.append(card);
   }
   panel.querySelector('[data-additional-audit]').replaceChildren(...data.audit.map(row=>element('p',`${row.occurred_at} · Користувач №${row.actor_id} · ${row.operation} · ${JSON.stringify(ProfileDates.display(row.changes))}`,'small text-break')));
   panel.dispatchEvent(new CustomEvent('profile:records-loaded',{bubbles:true}));
  }
  async function load(){data=await request(url);render();}
  async function connect(){try{const me=await request('/auth/me');csrf=me.csrf_token;await load();panel.querySelector('[data-additional-auth]').hidden=true;panel.querySelector('[data-additional-content]').hidden=false;}catch(error){message(error.message);panel.querySelector('[data-additional-auth]').hidden=false;}}
  panel.querySelector('[data-additional-new]').addEventListener('click',()=>open());
  panel.querySelector('[data-additional-cancel]').addEventListener('click',()=>{ProfileUI.resetForm(form);ProfileUI.closeEditor(editor);editing=null;message('');});
  panel.querySelector('[data-additional-reload]').addEventListener('click',connect);
  form.addEventListener('submit',async event=>{event.preventDefault();if(pending)return;pending=true;const button=form.querySelector('button:not([type])');button.disabled=true;message('');
   try{const updating=!!editing,values=Object.fromEntries(data.fields.map(([key])=>[key,form.elements.namedItem(key).value||null]));
    for(const input of form.querySelectorAll('[data-family-geo-id]'))values[input.name]=input.value||null;
    const result=await request(url+(editing?'/'+editing.id:''),{fields:values,revision:editing?.revision});await load();ProfileUI.finishRecord(editor,form,updating);editing=null;
    const notice=panel.querySelector('[data-additional-message]');notice.textContent=(result.warnings||[]).join(' ');notice.className=notice.textContent?'alert alert-warning':'';
   }catch(error){message(error.message);ProfileUI.openEditor(editor);}finally{pending=false;button.disabled=false;}
  });
  document.querySelector('#tab-'+kind)?.addEventListener('shown.bs.tab',connect);connect();
 }
})();

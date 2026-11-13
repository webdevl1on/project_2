/* Read-only polling does not extend sessions. Writes are never replayed after MFA. */
(()=>{'use strict';
 const root=document.querySelector('[data-backup-panel]');if(!root)return;
 const get=s=>root.querySelector(s),message=get('[data-backup-message]');
 let state=JSON.parse(get('[data-backup-state]').textContent);
 const labels={VERIFIED:'Цілісність підтверджено',SUCCESS:'Успішно',FAILED:'Помилка',NOT_RUN:'Ще не виконано',NOT_CONFIGURED:'Не налаштовано',CORRUPT:'Пошкоджено',MISSING:'Відсутнє',QUEUED:'У черзі',RUNNING:'Виконується'};
 const el=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
 const size=v=>v==null?'—':(v/1024**2).toLocaleString('uk-UA',{maximumFractionDigits:2})+' МіБ';
 async function request(url,body){
  const response=await fetch(url,body!==undefined?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  const data=await response.json();
  if(!response.ok)throw Error(String(data.detail||'').includes('MFA_REAUTH_REQUIRED')?'Підтвердьте особу та повторно натисніть кнопку операції.':data.detail||'Не вдалося виконати дію.');
  return data;
 }
 function render(){
  get('[data-backup-drill]').textContent=state.last_drill?state.last_drill.at+' · '+Number(state.last_drill.details.restore_seconds).toFixed(2)+' с':state.drill_configured?'Очікує виконання':'Не налаштовано або ще не виконувалося';
  const warning=get('[data-backup-warning]');warning.hidden=state.configured&&!state.rpo_overdue&&!state.external_overdue&&!state.statistics?.low_space;
  warning.textContent=state.configured?(state.statistics?.low_space?'Недостатньо вільного місця. Перевірте сховища; автоматичного очищення немає.':'Немає копії з успішним тестовим відновленням за останню годину або прострочено зовнішню репліку. Перевірте worker і планувальник.'):state.message;
  get('[data-backup-last]').textContent=state.last_success?.snapshot_at||'Ще немає копії з успішним drill';
  get('[data-backup-failure]').textContent=state.last_failure?state.last_failure.at+' · '+state.last_failure.code:'Не зафіксовано';
  get('[data-backup-next]').textContent=state.next_at||'Не налаштовано';
  get('[data-backup-external]').textContent=state.external_configured?(state.external_available?'Доступне; результат репліки наведено нижче':'Недоступне'):'Не налаштовано';
  get('[data-backup-create]').hidden=!state.can_run;
  get('[data-emergency-create]').hidden=!state.can_export;get('[data-usb-open]').hidden=!state.can_export;
  get('[data-storage-refresh]').hidden=!state.can_run;
  get('[data-emergency-last]').textContent=state.emergency?'Остання версія: '+state.emergency.at:'Готових версій ще немає';
  const list=get('[data-backup-list]');list.replaceChildren();
  for(const b of state.backups){
   const row=el('tr','');
   for(const value of [b.snapshot_at,b.schedule==='daily'?'Щоденна повна':b.schedule==='hourly'?'Щогодинна повна':b.kind==='full'?'Повна':'Самодостатня точка',size(b.size),labels[b.integrity]||b.integrity,b.drill==='SUCCESS'?'Тестове відновлення успішне':labels[b.drill||'NOT_RUN'],labels[b.external]||b.external])row.append(el('td',value));
   const actions=el('td','');
   if(state.can_run&&b.integrity!=='PRUNED'){const button=el('button','Перевірити');button.type='button';button.className='btn btn-sm btn-outline-primary';button.addEventListener('click',()=>run('/verify/'+b.id));actions.append(button);}
   row.append(actions);list.append(row);
  }
  const statistics=get('[data-storage-statistics]');statistics.replaceChildren();
  if(state.statistics){const s=state.statistics;for(const [label,value] of [['Виміряно (UTC)',s.at],['PostgreSQL',size(s.database_size)],['Повні копії',size(s.backups.size)+' · '+s.backups.count+' копій'],['Excel',size(s.excel.size)+' · '+s.excel.files+' файлів'],['Фото та документи',size(s.documents.size)+' · '+s.documents.files+' файлів'],['Приріст від базового вимірювання',size(s.growth_7_days)],['Вільно: копії / Excel / документи',[s.backups.free,s.excel.free,s.documents.free].map(size).join(' / ')],['Остання успішна операція',s.last_success||'—'],['Остання невдала операція',s.last_failure||'—']]){const term=el('dt',label),description=el('dd',value);term.className='col-sm-5';description.className='col-sm-7';statistics.append(term,description);}}
  else statistics.append(el('dd','Вимірювань ще немає.'));
  get('[data-backup-jobs]').replaceChildren(...state.jobs.map(j=>el('p',`${j.at} · ${j.operation} · ${labels[j.state]||j.state} · спроба ${j.attempts||0}${j.code?' · '+j.code:''}`)));
  get('[data-backup-events]').replaceChildren(...state.events.slice(-10).reverse().map(e=>el('p',`${e.at} · ${e.actor_user_id?'Користувач ID '+e.actor_user_id:'Серверна операція'} · ${e.operation} · ${labels[e.result]||e.result}${e.code?' · '+e.code:''}${e.details?.files!=null?' · '+e.details.files+' файлів · '+size(e.details.size):''}`)));
 }
 async function load(){try{state=await request('/admin/backups/data');render();}catch(error){message.textContent=error.message;}}
 async function run(path,body={}){try{const result=await request('/admin/backups'+path,body);message.textContent='Завдання '+result.id+' прийнято worker. Результат з’явиться в журналі.';await load();}catch(error){message.textContent=error.message;}}
 get('[data-backup-create]').addEventListener('click',()=>run('/create'));
 get('[data-backup-refresh]').addEventListener('click',load);
 get('[data-emergency-create]').addEventListener('click',()=>run('/emergency'));
 get('[data-storage-refresh]').addEventListener('click',()=>run('/statistics'));
 get('[data-usb-open]').addEventListener('click',async()=>{
  try{const volumes=await request('/admin/backups/volumes'),select=get('[data-usb-volume]');select.replaceChildren();
   for(const v of volumes){const option=el('option',`${v.label||'USB'} · ${v.root} · вільно ${size(v.free)}${v.eligible?'':' · BitLocker недоступний'}`);option.value=v.id;option.disabled=!v.eligible;select.append(option);}
   get('[data-usb-picker]').hidden=false;get('[data-usb-confirm]').disabled=!volumes.some(v=>v.eligible);if(!volumes.length)message.textContent='Дозволених USB на сервері не знайдено.';
  }catch(error){message.textContent=error.message;}
 });
 get('[data-usb-confirm]').addEventListener('click',()=>{const id=get('[data-usb-volume]').value;if(id)run('/usb',{volume_id:id});});
 render();setInterval(()=>{if(!document.hidden)load();},30000);
})();

/* Local calendar + 24-hour time; preserve the original named datetime-local ISO contract. */
(function(root,factory){const api=factory(typeof module==='object'&&module.exports?require('./profile_dates.js'):root.ProfileDates);if(typeof module==='object'&&module.exports)module.exports=api;else{root.ProfileDateTimes=api;api.enhance(document.querySelector('[data-access-admin]'));}})(globalThis,dates=>{
 'use strict';
 function compose(day,time){if(!day&&!time)return '';if(!day||!time)throw Error('Вкажіть повну дату та час.');const iso=dates.parse(day),match=/^(\d{2}):(\d{2})$/.exec(time);if(!match||+match[1]>23||+match[2]>59)throw Error('Вкажіть час у форматі ГГ:ХХ (00:00–23:59).');return iso+'T'+time;}
 function enhance(scope){if(!scope)return;
  for(const canonical of scope.querySelectorAll('input[type="datetime-local"]')){
   const wrapper=document.createElement('span'),day=document.createElement('input'),time=document.createElement('input');wrapper.className='access-datetime';
   const label=canonical.closest('label')?.textContent.trim()||'Дата й час';
   day.type='date';day.className='form-control';day.required=canonical.required;day.setAttribute('aria-label',label+' — дата');
   time.type='text';time.className='form-control access-time';time.placeholder='ГГ:ХХ';time.inputMode='numeric';time.maxLength=5;time.setAttribute('aria-label',label+' — час, 24 години');time.dataset.datetimeTimeFor=canonical.name;
   canonical.before(wrapper);wrapper.append(canonical,day,time);canonical.type='hidden';dates.enhance(wrapper);
   const visible=wrapper.querySelector('[data-exact-date-for]');visible.dataset.datetimeDateFor=canonical.name;
   const descriptor=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
   const sync=()=>{const value=descriptor.get.call(canonical);day.value=value.slice(0,10);time.value=value.slice(11,16);time.required=canonical.required||Boolean(value);time.disabled=canonical.disabled;day.disabled=canonical.disabled;time.setCustomValidity('');};
   Object.defineProperty(canonical,'value',{configurable:true,get(){return descriptor.get.call(this);},set(value){descriptor.set.call(this,value||'');sync();}});
   const entered=()=>{try{const value=compose(visible.value,time.value);if(value&&((canonical.min&&value<canonical.min)||(canonical.max&&value>canonical.max)))throw Error('Дата й час поза дозволеним діапазоном.');descriptor.set.call(canonical,value);time.setCustomValidity('');}catch(e){descriptor.set.call(canonical,'');time.setCustomValidity(e.message);}time.required=canonical.required||Boolean(visible.value);canonical.dispatchEvent(new Event('change',{bubbles:true}));};
   day.addEventListener('input',entered);day.addEventListener('change',entered);time.addEventListener('input',entered);
   canonical.form?.addEventListener('reset',()=>setTimeout(sync,0));sync();
  }
 }
 return {compose,enhance};
});

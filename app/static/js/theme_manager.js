/* Synchronous first-paint theme. A replaceable adapter permits future profile storage. */
(function(root,factory){
 const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
 if(!root.document)return;root.ProjectTheme=api;
 let storage;try{storage=root.localStorage;}catch(_){}
 api.apply(api.read(storage),root.document);
 root.addEventListener('storage',e=>{if(e.key===api.STORAGE_KEY||e.key===null){const theme=api.apply(api.normalize(e.newValue),root.document);root.document.dispatchEvent(new CustomEvent('project2:theme-change',{detail:{theme,saved:true,source:'storage'}}));}});
 root.document.addEventListener('DOMContentLoaded',()=>root.document.querySelectorAll('[data-theme-select]').forEach(select=>{
  select.replaceChildren(...Object.entries(api.themes).map(([key,label])=>new Option(label,key)));select.value=root.document.documentElement.dataset.theme;select.addEventListener('change',()=>api.set(select.value,root.document));
 }));
})(globalThis,()=>{
 'use strict';const STORAGE_KEY='project2:ui-theme';
 const themes=Object.freeze({light:'Світла',dark:'Темна',military:'Мілітарі'});
 const bootstrapModes=Object.freeze({light:'light',dark:'dark',military:'light'});
 const normalize=value=>Object.hasOwn(themes,value)?value:'light';
 let adapter={read(storage){try{return storage?.getItem(STORAGE_KEY);}catch(_){return null;}},write(value){try{globalThis.localStorage.setItem(STORAGE_KEY,value);return true;}catch(_){return false;}}};
 const api={STORAGE_KEY,themes,bootstrapModes,normalize,read(storage){return normalize(adapter.read(storage));},
  apply(value,document){const theme=normalize(value);document.documentElement.dataset.theme=theme;document.documentElement.dataset.bsTheme=bootstrapModes[theme]||'light';document.querySelectorAll('[data-theme-select]').forEach(s=>{s.value=theme;});return theme;},
  set(value,document){const theme=api.apply(value,document),saved=adapter.write(theme);document.dispatchEvent(new CustomEvent('project2:theme-change',{detail:{theme,saved}}));const feedback=document.querySelector('[data-theme-feedback]');if(feedback)feedback.textContent=saved?'':'Тему застосовано. Браузер не дозволяє зберегти вибір.';return theme;},
  useAdapter(next){if(typeof next?.read!=='function'||typeof next?.write!=='function')throw new TypeError('Invalid theme adapter');adapter=next;}
 };return api;
});

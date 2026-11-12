/* Advisory only: the service remains the authority for assignment/version periods. */
(()=>{
 const selection=document.querySelector('[data-staff-selection] form');if(!selection)return;
 selection.elements.structure_id.addEventListener('change',()=>{selection.elements.version_id.value='';selection.requestSubmit();});
 const form=document.querySelector('[data-staff-version-correction]');if(!form)return;
 const periods=JSON.parse(document.querySelector('[data-staff-assignment-periods]').textContent),warning=form.querySelector('[data-staff-period-warning]');
 const check=()=>{const start=form.elements.valid_from.value,end=form.elements.valid_to.value;warning.hidden=!periods.some(p=>start&&p.start<start||end&&(!p.end||p.end>end));};
 form.addEventListener('change',check);form.addEventListener('input',check);check();
})();

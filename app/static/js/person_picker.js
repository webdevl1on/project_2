/* Search/display only; availability is supplied by the server, writes revalidate. */
(() => {
    'use strict';
    document.querySelectorAll('[data-person-picker]').forEach(root => {
        const search=root.querySelector('.person-search'),value=root.querySelector('[data-person-value]');
        const options=Array.from(root.querySelectorAll('[data-person-option]'));
        const label=root.querySelector('[data-person-label]');
        const show=option=>{label.textContent=option.dataset.personName || '— Звільнити посаду —';};
        const initial=options.find(option=>option.dataset.personOption===value.value);
        if(initial)show(initial);
        value.form?.addEventListener('reset',()=>queueMicrotask(()=>{
            const original=options.find(option=>option.dataset.personOption===value.value);if(original)show(original);
            search.value='';search.dispatchEvent(new Event('input'));
        }));
        search.addEventListener('input',()=>{
            const query=search.value.trim().toLocaleLowerCase('uk');let count=0;
            options.forEach(option=>{option.hidden=Boolean(option.dataset.personOption)&&!option.dataset.personSearch.toLocaleLowerCase('uk').includes(query);if(!option.hidden&&option.dataset.personOption)count++;});
            root.querySelector('[data-person-no-results]').hidden=Boolean(count);
        });
        options.forEach(option=>option.addEventListener('click',()=>{
            value.value=option.dataset.personOption;show(option);
            bootstrap.Dropdown.getOrCreateInstance(label).hide();
            root.dispatchEvent(new CustomEvent('personpicked',{bubbles:true,detail:{positionId:option.dataset.personPosition || ''}}));
        }));
    });
})();

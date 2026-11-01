/* Existing import date controls, now hosted in administration. */
(() => {
    document.querySelectorAll('[data-current-version]').forEach(input=>input.addEventListener('change',()=>{
        const end=input.form.elements.valid_to;
        if(input.checked)end.value='';end.disabled=input.checked;end.required=!input.checked;
    }));
})();

/* Stable in-page tabs and a read-only overview refreshed from source records. */
(() => {
    const tabs=document.querySelector('#personTabs'); if(!tabs)return;
    let generation=0, pendingRecord=null;
    const recordHash=/^(exams|injuries|awards|dna|tasks|documents|education|family|directives|contacts|service-bases)-(\d+)$/;
    function revealRecord(){
        if(!pendingRecord)return;
        const {key,id}=pendingRecord,scope=document.getElementById(key);
        const record=scope?.querySelector(`[data-medical-record="${id}"],[data-document-card="${id}"],[data-additional-record="${id}"],[data-contact-id="${id}"],[data-service-basis="${id}"]`);
        if(!record){
            const filter=scope?.querySelector('[data-task-history],[data-document-history]');
            const loaded=scope?.querySelector('[data-medical-content],[data-document-content]');
            if(filter&&!filter.checked&&loaded&&!loaded.hidden){filter.checked=true;filter.dispatchEvent(new Event('change'));}
            return;
        }
        const card=record.tagName==='DETAILS'?record:record.querySelector('[data-record-card],[data-contact-card]');
        if(!card)return;
        card.open=true;
        pendingRecord=null;requestAnimationFrame(()=>card.scrollIntoView({block:'nearest'}));
    }
    window.refreshProfileOverview=async()=>{
        const target=document.querySelector('#profile-overview'), token=++generation;
        try { const response=await fetch(target.dataset.url,{cache:'no-store'});
            if(!response.ok)throw new Error(); const html=await response.text();
            if(token===generation)target.innerHTML=html;
        } catch (_) { /* Existing overview remains visible and can be retried on the next visit. */ }
    };
    function show(key,block) {
        const trigger=[...tabs.querySelectorAll('[data-bs-target]')].find(button=>button.getAttribute('data-bs-target')==='#'+key);if(!trigger)return;
        bootstrap.Tab.getOrCreateInstance(trigger).show();
        if(['birthplace','registration','actual','correspondence'].includes(block)) {
            const section=document.querySelector(`[data-geo-block="${block}"]`);
            if(section) {section.querySelector('details').open=true;requestAnimationFrame(()=>section.scrollIntoView({block:'nearest'}));}
        }
    }
    function fromUrl() {
        const hash=location.hash.slice(1), query=new URLSearchParams(location.search).get('tab');
        const record=recordHash.exec(hash);pendingRecord=record?{key:record[1],id:record[2]}:null;
        if(record){show(record[1]);revealRecord();}
        else if(hash.startsWith('addresses-'))show('addresses',hash.slice(10));else show(hash||query||'general');
    }
    document.addEventListener('click',event=>{
        const link=event.target.closest('[data-profile-tab]');if(!link)return;
        event.preventDefault();show(link.dataset.profileTab,link.dataset.profileBlock);
        history.replaceState(null,'',link.getAttribute('href'));
    });
    tabs.addEventListener('shown.bs.tab',event=>{
        const key=event.target.getAttribute('data-bs-target').slice(1);
        const record=recordHash.exec(location.hash.slice(1));
        if(!(key==='addresses' && location.hash.startsWith('#addresses-'))&&record?.[1]!==key)history.replaceState(null,'','#'+key);
        if(key==='general')window.refreshProfileOverview();
    });
    document.addEventListener('profile:records-loaded',revealRecord);
    new MutationObserver(revealRecord).observe(document.querySelector('.tab-content'),{childList:true,subtree:true});
    window.addEventListener('hashchange',fromUrl);fromUrl();
})();

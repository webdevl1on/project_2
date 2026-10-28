/* Stable in-page tabs and a read-only overview refreshed from source records. */
(() => {
    const tabs=document.querySelector('#personTabs'); if(!tabs)return;
    let generation=0;
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
        if(hash.startsWith('addresses-'))show('addresses',hash.slice(10));else show(hash||query||'general');
    }
    document.addEventListener('click',event=>{
        const link=event.target.closest('[data-profile-tab]');if(!link)return;
        event.preventDefault();show(link.dataset.profileTab,link.dataset.profileBlock);
        history.replaceState(null,'',link.getAttribute('href'));
    });
    tabs.addEventListener('shown.bs.tab',event=>{
        const key=event.target.getAttribute('data-bs-target').slice(1);
        if(!(key==='addresses' && location.hash.startsWith('#addresses-')))history.replaceState(null,'','#'+key);
        if(key==='general')window.refreshProfileOverview();
    });
    window.addEventListener('hashchange',fromUrl);fromUrl();
})();

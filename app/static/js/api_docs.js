/* Official documentation widgets, inside the unchanged API/security boundary. */
(()=>{
 const panel=document.querySelector('[data-api-kind]');if(!panel)return;
 if(panel.dataset.apiKind==='swagger'){
  window.ui=SwaggerUIBundle({url:'/openapi.json',dom_id:'#swagger-ui',deepLinking:true,layout:'BaseLayout',showExtensions:true,showCommonExtensions:true,presets:[SwaggerUIBundle.presets.apis,SwaggerUIBundle.SwaggerUIStandalonePreset]});
 }else{
  let running=false,again=false,search='';
  const render=()=>{
   const input=panel.querySelector('input');if(input)search=input.value;
   if(running){again=true;return;}running=true;
   const style=getComputedStyle(document.documentElement),color=key=>style.getPropertyValue('--color-'+key).trim();
   Redoc.init('/openapi.json',{hideDownloadButton:false,theme:{colors:{primary:{main:color('primary')},text:{primary:color('text'),secondary:color('text-muted')}},sidebar:{backgroundColor:color('surface'),textColor:color('text')},rightPanel:{backgroundColor:color('surface-secondary'),textColor:color('text')},typography:{fontFamily:'system-ui, sans-serif',headings:{fontFamily:'system-ui, sans-serif'}}}},document.getElementById('redoc'),()=>{
    const next=panel.querySelector('input');if(next&&search){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(next,search);next.dispatchEvent(new Event('input',{bubbles:true}));}
    running=false;if(again){again=false;render();}
   });
  };
  render();document.addEventListener('project2:theme-change',render);
 }
})();

const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
module.exports=async({context,base})=>{
 const folder='/tmp/project2-ui-widget-assets';fs.mkdirSync(folder,{recursive:true});
 for(const [name,url] of [
 ['swagger.css','https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css'],
 ['swagger.js','https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js'],
 ['redoc.js','https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js']]){
  const file=path.join(folder,name);if(!fs.existsSync(file))fs.writeFileSync(file,execFileSync('curl',['--fail','--silent','--show-error','--location','--max-time','60',url],{maxBuffer:32*1024*1024}));
  await context.route(url,route=>route.fulfill({body:fs.readFileSync(file),contentType:name.endsWith('.css')?'text/css':'application/javascript'}));
 }
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{for(const url of ['/docs','/redoc']){
  const ready=page.locator(url==='/docs'?'.swagger-ui .info':'.redoc-wrap h1');
  await page.goto(base+url);await ready.waitFor({timeout:30000});
  if(url==='/redoc')await page.locator('#redoc input').first().fill('Person');
  for(const theme of ['light','dark','military']){
   await page.getByRole('button',{name:'Меню користувача та тема оформлення'}).click();await page.locator('[data-theme-select]').selectOption(theme);await page.keyboard.press('Escape');
   await ready.waitFor({timeout:30000});
   if(url==='/redoc')assert.equal(await page.locator('#redoc input').first().inputValue(),'Person');
   await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  await page.setViewportSize({width:1280,height:900});await page.screenshot({path:'/tmp/project2-ui-screenshots/api-'+url.slice(1)+'-military.png'});
  console.log('PASS UI API: '+url+' retains its real protected widget inside the shared responsive shell');
 }assert.deepEqual(errors,[]);}finally{await page.close();}
};

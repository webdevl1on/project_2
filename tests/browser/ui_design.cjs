const assert=require('node:assert/strict'),fs=require('node:fs');
module.exports=async({context,base,assets,adminToken})=>{
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const directory='/tmp/project2-ui-screenshots';fs.mkdirSync(directory,{recursive:true});
 async function theme(value){await page.getByRole('button',{name:'Меню користувача та тема оформлення'}).click();await page.locator('[data-theme-select]').selectOption(value);assert.equal(await page.locator('html').getAttribute('data-theme'),value);await page.keyboard.press('Escape');}
 async function open(){await page.getByRole('button',{name:'Відкрити головне меню',exact:true}).click();await page.locator('#app-sidebar.show').waitFor();}
 const luminance=hex=>{const s=hex.trim().replace('#',''),rgb=[0,2,4].map(i=>parseInt(s.slice(i,i+2),16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
 try{
  await page.setViewportSize({width:1280,height:900});await page.goto(base+'/person-positions');
  for(const mode of ['light','dark','military']){
   await theme(mode);await page.reload();assert.equal(await page.locator('html').getAttribute('data-theme'),mode);
   const pairs=await page.evaluate(()=>{const c=getComputedStyle(document.documentElement),v=k=>c.getPropertyValue('--color-'+k).trim();return [['text','surface'],['text-muted','surface'],['primary','surface'],['success','success-bg'],['warning','warning-bg'],['danger','danger-bg'],['info','info-bg'],['nav-text','nav'],['sidebar-text','sidebar']].map(([a,b])=>[a,v(a),v(b)]);});
   for(const [name,a,b] of pairs){const values=[luminance(a),luminance(b)].sort((x,y)=>y-x);assert.ok((values[0]+.05)/(values[1]+.05)>=4.5,mode+' contrast '+name);}
   const before=await page.locator('.table-viewport').boundingBox();await open();const after=await page.locator('.table-viewport').boundingBox();assert.ok(Math.abs(before.width-after.width)<1&&Math.abs(before.x-after.x)<1);
   assert.ok(await page.locator('#app-sidebar').evaluate(n=>n.contains(document.activeElement)));
   await page.screenshot({path:`${directory}/staff-${mode}-menu.png`});await page.keyboard.press('Escape');await page.locator('#app-sidebar.show').waitFor({state:'hidden'});
   assert.equal(await page.getByRole('button',{name:'Відкрити головне меню',exact:true}).getAttribute('aria-expanded'),'false');
  }
  console.log('PASS UI: all themes persist; overlay preserves table geometry, traps focus and closes with Escape');
  await open();await page.locator('#app-sidebar a[href="/persons"]').click();await page.waitForURL(base+'/persons');assert.equal(await page.locator('#app-sidebar.show').count(),0);
  await open();await page.locator('.offcanvas-backdrop').click({position:{x:800,y:100}});await page.locator('#app-sidebar.show').waitFor({state:'hidden'});
  console.log('PASS UI: real navigation and backdrop close the sidebar');
  for(const mode of ['light','dark','military'])for(const width of [390,768,1280,1920]){
   await page.setViewportSize({width,height:900});await page.goto(base+'/person-positions');await theme(mode);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${mode}/${width} body overflow`);
   await page.screenshot({path:`${directory}/staff-${mode}-${width}.png`});
  }
  console.log('PASS UI: three themes at 390/768/1280/1920 retain a bounded table viewport');
  await page.setViewportSize({width:1280,height:900});await page.goto(base+'/person_full_info/1');
  const settings=page.locator('[data-profile-layout-settings]');await settings.locator('summary').click();
  await settings.getByRole('button',{name:'Особисті дані: перемістити нижче',exact:true}).click();assert.equal(await page.locator('[data-profile-cards]>[data-profile-card]').first().getAttribute('data-profile-card'),'service');
  await settings.locator('label').filter({hasText:'Адреси'}).locator('input').uncheck();assert.equal(await page.locator('[data-profile-card="addresses"]').isHidden(),true);
  await page.reload();assert.equal(await page.locator('[data-profile-card="addresses"]').isHidden(),true);await settings.locator('summary').click();await settings.locator('[data-profile-layout-reset]').click();assert.equal(await page.locator('[data-profile-card="addresses"]').isVisible(),true);
  await page.screenshot({path:`${directory}/profile-military-1280.png`});
  console.log('PASS UI: profile blocks reorder/hide/persist/reset without touching personnel data');
  await page.goto(base+'/person_full_info/1#events');await page.locator('[data-events-open]').click();await page.locator('#person-events-modal.show').waitFor();await page.locator('#person-events-modal [data-events-list]').waitFor();await page.locator('#person-events-modal .btn-close').click();await page.locator('#person-events-modal.show').waitFor({state:'hidden'});
  console.log('PASS UI: full profile opens the existing personnel events modal');
  await page.goto(base+'/person_full_info/1#documents');await page.waitForLoadState('networkidle');const records=page.locator('[data-document-current-list]');await records.locator('.ui-record-body').first().waitFor({state:'attached'});
  const firstRecord=records.locator(':scope > details').first(),secondRecord=records.locator(':scope > details').nth(1);
  await firstRecord.locator(':scope > summary').click();assert.equal(await firstRecord.locator('.ui-record-body').evaluate(n=>getComputedStyle(n).position),'absolute');
  await secondRecord.locator(':scope > summary').click();await firstRecord.locator('.ui-record-body').waitFor({state:'hidden'});assert.equal(await firstRecord.evaluate(n=>n.open),false);assert.equal(await secondRecord.evaluate(n=>n.open),true);
  const presence=secondRecord.locator('select[name=presence]');await presence.selectOption('PRESENT');await theme('light');assert.equal(await presence.inputValue(),'PRESENT');
  await page.setViewportSize({width:390,height:844});assert.equal(await secondRecord.locator('.ui-record-body').evaluate(n=>getComputedStyle(n).position),'static');
  await page.screenshot({path:`${directory}/documents-light-390.png`});await page.setViewportSize({width:1280,height:900});await page.screenshot({path:`${directory}/documents-light-1280.png`});
  console.log('PASS UI: shared record list/detail reuses original controls, retains unsaved values and adapts to mobile');
  await page.goto(base+'/persons/1/edit');const surname=page.locator('[name=surname]');await surname.fill('Незбережена чернетка');await theme('dark');assert.equal(await surname.inputValue(),'Незбережена чернетка');
  for(const route of ['/admin','/admin/users','/admin/access','/admin/organization','/admin/staff','/admin/backups','/events','/staff/history','/account/security','/account/sessions']){
   await page.setViewportSize({width:390,height:844});const response=await page.goto(base+route);assert.equal(response.status(),200,route);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),route+' overflow');
  }
  console.log('PASS UI: drafts survive theme changes; administrative, security and working pages remain usable at 390 px');
  const anonymous=await context.browser().newContext();try{
   await anonymous.route('https://cdn.jsdelivr.net/npm/bootstrap@*/dist/**',route=>{const url=route.request().url(),file=url.split('/dist/')[1],version=url.split('bootstrap@')[1].split('/')[0];return route.fulfill({body:assets[`${version}/${file}`],contentType:file.endsWith('.js')?'application/javascript':'text/css'});});
   await anonymous.addInitScript(()=>localStorage.setItem('project2:ui-theme','dark'));const login=await anonymous.newPage();login.on('pageerror',e=>errors.push(e.message));await login.goto(base+'/auth/login');assert.equal(await login.locator('html').getAttribute('data-theme'),'dark');assert.equal(await login.locator('#app-sidebar').count(),0);assert.equal(await login.locator('input[name=username]').evaluate(n=>getComputedStyle(n).display),'block');await login.screenshot({path:`${directory}/login-dark-1280.png`});
   const first=await anonymous.request.post(base+'/auth/login',{data:{username:'browser-admin',password:adminToken}});assert.equal(first.status(),200);await login.goto(base+'/auth/mfa');await login.locator('[data-mfa-mode="flow"]').waitFor();
   for(const mode of ['light','dark','military']){await login.getByRole('button',{name:'Меню користувача та тема оформлення'}).click();await login.locator('[data-theme-select]').selectOption(mode);await login.keyboard.press('Escape');assert.equal(await login.locator('html').getAttribute('data-theme'),mode);await login.screenshot({path:`${directory}/mfa-${mode}-1280.png`});}
  }finally{await anonymous.close();}
  await page.evaluate(()=>localStorage.setItem('project2:ui-theme','invalid-saved-value'));await page.reload();assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
  assert.deepEqual(errors,[]);console.log('PASS UI: login/MFA use all themes, invalid saved values fall back safely, and no JavaScript errors occur');
  const {chromium}=require('playwright'),os=require('node:os'),path=require('node:path'),profile=fs.mkdtempSync(path.join(os.tmpdir(),'project2-ui-restart-'));
  const launch=async()=>{const own=await chromium.launchPersistentContext(profile,{executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});await own.route('https://cdn.jsdelivr.net/npm/bootstrap@*/dist/**',route=>{const url=route.request().url(),file=url.split('/dist/')[1],version=url.split('bootstrap@')[1].split('/')[0];return route.fulfill({body:assets[`${version}/${file}`],contentType:file.endsWith('.js')?'application/javascript':'text/css'});});return own;};
  let persistent;try{persistent=await launch();const first=await persistent.newPage();await first.goto(base+'/auth/login');await first.getByRole('button',{name:'Меню користувача та тема оформлення'}).click();await first.locator('[data-theme-select]').selectOption('military');await persistent.close();persistent=await launch();const restored=await persistent.newPage();await restored.goto(base+'/auth/login');assert.equal(await restored.locator('html').getAttribute('data-theme'),'military');console.log('PASS UI: theme survives a real Chromium process restart with an isolated persistent profile');}finally{await persistent?.close();fs.rmSync(profile,{recursive:true,force:true});}
 }finally{await page.close();}
};

const assert=require('node:assert/strict');
module.exports=async({context,base,adminToken})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const scenario=async(name,fn)=>{await fn();console.log(`PASS history forms: ${name}`);};
    const values=form=>form.evaluate(node=>Array.from(new FormData(node).entries()));
    try{
        await page.goto(base+'/staff/history');
        await page.locator('[data-position-id="1"] > summary').click();
        await page.locator('[data-history-add="1"]').click();
        const form=page.locator('[data-history-editor]');
        const section=page.locator('#history-editor');await section.waitFor({state:'visible'});
        await form.locator('[data-person-label]').click();await form.locator('[data-person-option="3"]').click();
        await form.locator('[data-exact-date-for="assigned_from"]').fill('02.02.2026');
        await form.locator('[data-exact-date-for="assigned_to"]').fill('01.01.2026');
        const url=page.url();let navigations=0;page.on('framenavigated',()=>navigations++);
        await scenario('invalid date order preserves person, position and dates without navigation',async()=>{
            const before=await values(form);await form.locator('[type=submit]').click();
            await form.locator('[data-history-form-error]').filter({hasText:'раніше'}).waitFor();
            assert.deepEqual(await values(form),before);assert.equal(page.url(),url);assert.equal(navigations,0);
            assert.equal(await section.isVisible(),true);
            const field=form.locator('[data-exact-date-for="assigned_to"]');
            assert.equal(await field.getAttribute('aria-invalid'),'true');assert.equal(await field.evaluate(n=>n===document.activeElement),true);
        });
        await scenario('server overlap keeps all values and the open editor',async()=>{
            await form.locator('[data-exact-date-for="assigned_to"]').fill('01.03.2026');
            const before=await values(form);await form.locator('[type=submit]').click();
            await form.locator('[data-history-form-error]').filter({hasText:/перетинаються|зайнята/}).waitFor();
            assert.deepEqual(await values(form),before);assert.equal(navigations,0);assert.equal(await section.isVisible(),true);
        });
        await scenario('network failure preserves input and allows retry',async()=>{
            await page.route('**/staff/assignments/prepare',route=>route.abort());
            const before=await values(form);await form.locator('[type=submit]').click();
            await form.locator('[data-history-form-error]').filter({hasText:'Немає зв’язку'}).waitFor();
            assert.deepEqual(await values(form),before);assert.equal(await form.locator('[type=submit]').isEnabled(),true);
            await page.unroute('**/staff/assignments/prepare');
        });
        await scenario('editing an assignment preserves the draft on date errors and stale revision',async()=>{
            await section.locator('[data-bs-dismiss="modal"]').first().click();await section.waitFor({state:'hidden'});
            await page.locator('[data-history-edit]').first().click();await section.waitFor({state:'visible'});
            await form.locator('[data-exact-date-for="assigned_from"]').fill('01.04.2026');await form.locator('[data-exact-date-for="assigned_to"]').fill('01.03.2026');
            const before=await values(form);await form.locator('[type=submit]').click();
            await form.locator('[data-history-form-error]').filter({hasText:'раніше'}).waitFor();assert.deepEqual(await values(form),before);
            await form.locator('[data-exact-date-for="assigned_to"]').fill('01.05.2026');
            await form.locator('[name="revision"]').evaluate(n=>n.value='999');
            const draft=await values(form);await form.locator('[type=submit]').click();
            await form.locator('[data-history-form-error]').filter({hasText:'змінився'}).waitFor();
            assert.deepEqual(await values(form),draft);assert.equal(await section.isVisible(),true);assert.equal(navigations,0);
        });
        await context.request.post(base+'/admin/login',{form:{token:adminToken}});await page.goto(base+'/admin/staff');navigations=0;
        await scenario('position and version refusals retain drafts; successful correction updates data',async()=>{
            const version=page.locator('form[action$="/correct"]').filter({has:page.locator('[name="valid_from"]')});
            await version.locator('..').locator(':scope > summary').click();
            await version.locator('[name="name"]').fill('Збережена чернетка');await version.locator('[name="valid_from"]').fill('2027-01-01');
            const before=await values(version);await version.locator('button').click();
            await version.locator('[data-history-form-error]:visible').waitFor();assert.deepEqual(await values(version),before);
            const position=page.locator('form[action^="/staff/positions/"]').first();await position.locator('..').locator(':scope > summary').click();
            await position.locator('[name="name_short"]').fill('Виправлена посада');
            await position.locator('[name="position_number"]').fill('20');
            const draft=await values(position);await position.locator('button').click();
            await position.locator('[data-history-form-error]').filter({hasText:'таким номером'}).waitFor();assert.deepEqual(await values(position),draft);
            assert.equal(await position.locator('[name="position_number"]').getAttribute('aria-invalid'),'true');
            assert.equal(navigations,0);
            await position.locator('[name="position_number"]').fill('010');
            await Promise.all([page.waitForNavigation(),position.locator('button').click()]);
            assert.ok((await page.locator('body').innerText()).includes('Реквізити посади виправлено'));
            assert.equal(await page.locator('form[action^="/staff/positions/"]').first().locator('[name="name_short"]').inputValue(),'виправлена посада');
            assert.deepEqual(errors,[]);
        });
    }finally{await page.close();}
};

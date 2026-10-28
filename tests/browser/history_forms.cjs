const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
    const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
    const scenario=async(name,fn)=>{await fn();console.log(`PASS history forms: ${name}`);};
    const values=form=>form.evaluate(node=>Array.from(new FormData(node).entries()));
    try{
        await page.goto(base+'/staff/history');
        const form=page.locator('form[action="/staff/assignments/create"]');
        const section=form.locator('..');await section.locator('summary').click();
        await form.locator('[data-person-label]').click();await form.locator('[data-person-option="3"]').click();
        await form.locator('[name="assigned_from"]').fill('2026-02-02');
        await form.locator('[name="assigned_to"]').fill('2026-01-01');
        const url=page.url();let navigations=0;page.on('framenavigated',()=>navigations++);
        await scenario('invalid date order preserves person, position and dates without navigation',async()=>{
            const before=await values(form);await form.locator('button[type=submit],button:not([type])').last().click();
            await form.locator('[data-history-form-error]').filter({hasText:'раніше'}).waitFor();
            assert.deepEqual(await values(form),before);assert.equal(page.url(),url);assert.equal(navigations,0);
            assert.equal(await section.getAttribute('open'),'');
            assert.equal(await form.locator('[name="assigned_to"]').getAttribute('aria-invalid'),'true');
            assert.equal(await form.locator('[name="assigned_to"]').evaluate(n=>n===document.activeElement),true);
        });
        await scenario('server overlap keeps all values and the expanded section',async()=>{
            await form.locator('[name="assigned_to"]').fill('2026-03-01');
            const before=await values(form);await form.locator('button:not([type])').click();
            await form.locator('[data-history-form-error]').filter({hasText:'перетинаються'}).waitFor();
            assert.deepEqual(await values(form),before);assert.equal(navigations,0);assert.equal(await section.getAttribute('open'),'');
        });
        await scenario('network failure preserves input and allows retry',async()=>{
            await page.route('**/staff/assignments/create',route=>route.abort());
            const before=await values(form);await form.locator('button:not([type])').click();
            await form.locator('[data-history-form-error]').filter({hasText:'Немає зв’язку'}).waitFor();
            assert.deepEqual(await values(form),before);assert.equal(await form.locator('button:not([type])').isEnabled(),true);
            await page.unroute('**/staff/assignments/create');
        });
        await scenario('editing an assignment preserves the draft on date errors and server refusal',async()=>{
            const edit=page.locator('form[action^="/staff/assignments/"][action$="/correct"]').first();
            await edit.locator('..').locator(':scope > summary').click();
            await edit.locator('[name="assigned_from"]').fill('2026-04-01');await edit.locator('[name="assigned_to"]').fill('2026-03-01');
            const before=await values(edit);await edit.locator('button:not([type])').click();
            await edit.locator('[data-history-form-error]').filter({hasText:'раніше'}).waitFor();assert.deepEqual(await values(edit),before);
            await edit.locator('[name="assigned_to"]').fill('2026-05-01');
            await edit.locator('[name="revision"]').evaluate(n=>n.value='999');
            const draft=await values(edit);await edit.locator('button:not([type])').click();
            await edit.locator('[data-history-form-error]').filter({hasText:'змінився'}).waitFor();
            assert.deepEqual(await values(edit),draft);assert.equal(await edit.locator('..').getAttribute('open'),'');assert.equal(navigations,0);
        });
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

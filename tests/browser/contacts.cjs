const assert=require('node:assert/strict');
module.exports=async({context,base})=>{
    const created=await context.request.post(base+'/persons/new',{form:{sex:'female',surname:'Тестенко',name:'Олена',patronymic:'Тестівна',rank_id:'1',tax_number:'9876054321'}});
    const url=(await created.text()).match(/href="(\/person_full_info\/\d+)"/)[1];
    const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
    await context.grantPermissions(['clipboard-read','clipboard-write']);
    await page.goto(base+url);
    assert.match(await page.locator('header h1').innerText(),/ТЕСТЕНКО Олена Тестівна/);
    assert.equal(await page.locator('header h1').innerText().then(s=>s.includes('мобілізацією')),false);
    assert.equal(await page.getByRole('img',{name:'Фотографію не додано'}).count(),1);
    assert.equal(await page.locator('#general').isVisible(),true);
    await page.getByRole('link',{name:'Редагувати контакти',exact:true}).click();
    await page.locator('#contacts').waitFor({state:'visible'});
    console.log('PASS contacts: compact honest header, photo placeholder and overview navigation');
    const root=page.locator('#person-contacts');
    const section=kind=>root.locator('section').filter({has:page.getByRole('heading',{name:kind==='phone'?'Телефонні номери':'Електронна пошта',exact:true})});
    async function add(kind,value){
        const block=section(kind);await block.locator('summary').filter({hasText:kind==='phone'?'Додати номер':'Додати email'}).click();
        const form=block.locator('details').last().locator('form');await form.locator('[name="value"]').fill(value);
        const done=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/contacts'));
        await form.getByRole('button',{name:'Зберегти',exact:true}).click();assert.equal((await done).status(),200);
        await root.locator('article').filter({hasText:value}).first().waitFor();await page.waitForFunction(()=>!document.querySelector('#person-contacts').hasAttribute('aria-busy'));
    }
    for(const number of ['+44 20 7946 0001','+44 20 7946 0002','+1 (202) 555-0103'])await add('phone',number);
    for(const email of ['first@example.invalid','second@example.invalid'])await add('email',email);
    await add('phone','+44 20 7946 0004');
    assert.equal(await root.locator('article').count(),6);
    const first=()=>root.locator('article').filter({hasText:'+44 20 7946 0001'});
    async function action(article,name){const done=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/contacts'));await article.getByRole('button',{name,exact:true}).click();assert.equal((await done).status(),200);await page.waitForFunction(()=>!document.querySelector('#person-contacts').hasAttribute('aria-busy'));await root.getByRole('status').filter({hasText:'Контакти збережено.'}).waitFor();}
    await action(first(),'Зробити основним');await action(root.locator('article').filter({hasText:'+44 20 7946 0002'}),'Зробити основним');
    await action(root.locator('article').filter({hasText:'first@example.invalid'}),'Зробити основним');
    await page.locator('[data-bs-target="#general"]').click();
    await page.locator('#profile-overview').getByRole('link',{name:'+44 20 7946 0002',exact:true}).waitFor();
    await page.locator('[data-bs-target="#contacts"]').click();
    console.log('PASS contacts: multiple values, fourth phone, independent primaries and live overview');
    await first().getByRole('button',{name:'Копіювати номер',exact:true}).click();
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'+44 20 7946 0001');
    await root.locator('article').filter({hasText:'first@example.invalid'}).getByRole('button',{name:'Копіювати email',exact:true}).click();
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),'first@example.invalid');
    assert.equal(await root.locator('a[href^="mailto:"]').count(),2);
    await first().locator('summary').click();const edit=first().locator('details form');
    await edit.locator('[name="value"]').fill('invalid phone');await edit.locator('[name="label"]').fill('Чернетка');
    const invalid=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/contacts'));
    await edit.getByRole('button',{name:'Зберегти',exact:true}).click();assert.equal((await invalid).status(),400);
    assert.equal(await edit.locator('[name="label"]').inputValue(),'Чернетка');assert.equal(await edit.locator('.is-invalid').count(),1);
    console.log('PASS contacts: copy, mailto and validation preserve the draft');
    const second=root.locator('article').filter({hasText:'+44 20 7946 0002'});
    page.once('dialog',dialog=>dialog.dismiss());await second.getByRole('button',{name:'Прибрати',exact:true}).click();assert.equal(await second.count(),1);
    page.once('dialog',dialog=>dialog.accept());await action(second,'Прибрати');
    assert.equal(await root.locator('article').filter({hasText:'+44 20 7946 0002'}).count(),0);
    await page.reload();await root.waitFor({state:'visible'});assert.equal(await page.locator('#contacts').isVisible(),true);
    console.log('PASS contacts: confirmed archive and direct hash navigation');
    const editable=root.locator('article').filter({hasText:'+44 20 7946 0001'});
    await editable.locator('summary').click();
    const form=editable.locator('details form');
    await form.locator('[name="value"]').fill('+44 20 7946 0011');
    await form.locator('[name="is_primary"]').check();
    const saved=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/contacts'));
    await form.getByRole('button',{name:'Зберегти',exact:true}).click();assert.equal((await saved).status(),200);
    await page.waitForFunction(()=>!document.querySelector('#person-contacts').hasAttribute('aria-busy'));
    await page.locator('[data-bs-target="#general"]').click();
    await page.locator('#profile-overview').getByRole('link',{name:'+44 20 7946 0011',exact:true}).waitFor();
    await page.locator('[data-bs-target="#contacts"]').click();
    console.log('PASS contacts: editing a contact refreshes its overview value without reload');

    await page.setViewportSize({width:375,height:812});
    for(const key of ['general','contacts','addresses','names','ranks']){
        await page.locator(`[data-bs-target="#${key}"]`).click();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,key);
    }
    assert.equal(await page.locator('#person-geography [data-geo-clear-form]').count(),3);
    console.log('PASS contacts: mobile layout and relocated address controls');
    assert.deepEqual(errors,[]);await page.close();
};

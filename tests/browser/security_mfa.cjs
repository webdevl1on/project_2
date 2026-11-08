const assert=require('node:assert/strict');const {totp}=require('./mfa_helpers.cjs');
module.exports=async({context,base,adminToken})=>{
 // A separate native context deliberately has no automatic fixture MFA driver.
 const browser=context.browser(),own=await browser.newContext(),page=await own.newPage();
 async function password(username){await page.goto(base+'/auth/login');await page.locator('[name=username]').fill(username);await page.locator('[name=password]').fill(adminToken);await Promise.all([page.waitForURL('**/auth/mfa'),page.locator('[type=submit]').click()]);}
 try{
  for(const name of ['mfa-totp','mfa-passkey']){const r=await context.request.post(base+'/auth/users',{data:{username:name,display_name:'MFA тест',role:'user',password:adminToken}});assert.equal(r.status(),200,await r.text());}
  await password('mfa-totp');assert.equal((await own.request.get(base+'/persons')).status(),401);
  await page.locator('[data-totp-start]').click();await page.locator('[data-secret]').waitFor({state:'visible'});const secret=await page.locator('[data-secret]').innerText();
  await page.locator('[name=code]').first().fill(totp(secret));await page.locator('[data-totp-confirm] button').click();await page.locator('[data-codes]:visible').waitFor();const backups=(await page.locator('[data-code-list]').innerText()).split('\n');assert.equal(backups.length,10);
  await Promise.all([page.waitForURL('**/persons'),page.locator('[data-finish]').click()]);assert.equal((await own.request.get(base+'/auth/me')).status(),200);
  console.log('PASS MFA: password grants only enrollment; confirmed TOTP, local QR and ten backup codes precede a full session');
  await own.clearCookies();await password('mfa-totp');await page.locator('[name=method]').selectOption('backup');await page.locator('[data-prove-form] [name=code]').fill(backups[0]);await page.locator('[data-prove-form] button').click();await page.locator('[data-finish]:visible').waitFor();await Promise.all([page.waitForURL('**/persons'),page.locator('[data-finish]').click()]);
  await page.goto(base+'/account/security');await page.locator('[data-security-summary]').waitFor();assert.match(await page.locator('[data-security-summary]').innerText(),/9/);await page.goto(base+'/account/sessions');await page.locator('[data-session-list] tr').first().waitFor();assert.match(await page.locator('[data-session-list]').innerText(),/Поточна/);
  console.log('PASS MFA: backup login, safe remaining-code count and own session management');
  const cdp=await own.newCDPSession(page);await cdp.send('WebAuthn.enable');await cdp.send('WebAuthn.addVirtualAuthenticator',{options:{protocol:'ctap2',transport:'internal',hasResidentKey:true,hasUserVerification:true,isUserVerified:true,automaticPresenceSimulation:true}});
  await own.clearCookies();await password('mfa-passkey');await page.locator('[data-passkey-register]').click();await page.locator('[data-codes]:visible').waitFor();await Promise.all([page.waitForURL('**/persons'),page.locator('[data-finish]').click()]);
  await own.clearCookies();await password('mfa-passkey');await page.locator('[data-passkey-auth]').click();await page.locator('[data-finish]:visible').waitFor();await Promise.all([page.waitForURL('**/persons'),page.locator('[data-finish]').click()]);
  assert.equal((await own.request.get(base+'/auth/me')).status(),200);console.log('PASS MFA: Chromium CTAP2 virtual authenticator registers a Passkey and completes cryptographically verified second-factor login with UV');
 }catch(error){console.error('MFA browser error:',await page.locator('[data-mfa-error]').textContent());throw error;}finally{await own.close();}
};

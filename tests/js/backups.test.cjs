const assert = require('node:assert/strict');
const test = require('node:test');
const {errorText, jobPresentation, pollDelay} = require('../../app/static/js/backups.js');

test('job cards describe worker states and only expire unclaimed manual authorization', () => {
  const deadline = '2026-07-01T15:10:00Z';
  const queued = {state: 'QUEUED', authorization_expires_at: deadline};
  const now = Date.parse(deadline);
  assert.match(jobPresentation(queued, now).text, /^У черзі/);
  assert.match(jobPresentation(queued, now + 1).text, /^Прострочено.*Project2-Backup/);
  assert.match(jobPresentation({state: 'QUEUED'}, now + 1).text, /^У черзі/);
  assert.equal(jobPresentation({...queued, state: 'RUNNING'}, now + 1).text, 'Виконується');
  assert.equal(jobPresentation({...queued, state: 'SUCCESS'}, now + 1).text, 'Готово');
  assert.match(jobPresentation({...queued, state: 'FAILED', code: 'BACKUP_AUTHORIZATION_EXPIRED'}, now + 1).text, /^Прострочено/);
  assert.equal(jobPresentation({state: 'FAILED', code: 'USB_COPY_FAILED'}).tone, 'danger');
  assert.equal(jobPresentation({state: 'FAILED', code: 'UNKNOWN_ERROR'}).text, 'Помилка: UNKNOWN_ERROR');
});

test('known errors are translated and polling returns to idle cadence after completion', () => {
  for (const code of ['EMERGENCY_GENERATION_FAILED', 'USB_COPY_FAILED', 'STORAGE_NTFS_ACL_REQUIRED',
    'USB_BITLOCKER_REQUIRED', 'USB_VOLUME_CHANGED_OR_NOT_ALLOWED', 'USB_INSUFFICIENT_SPACE',
    'BACKUP_AUTHORIZATION_EXPIRED', 'BACKUP_DRILL_FAILED', 'BACKUP_DRILL_APPROVAL_REQUIRED',
    'EMERGENCY_QUOTA_EXCEEDED', 'MFA_REAUTH_REQUIRED']) {
    assert.notEqual(errorText(code), code);
  }
  assert.equal(errorText('NEW_SERVER_CODE'), 'NEW_SERVER_CODE');
  assert.equal(pollDelay([{state: 'SUCCESS'}, {state: 'QUEUED'}]), 3000);
  assert.equal(pollDelay([{state: 'RUNNING'}]), 3000);
  assert.equal(pollDelay([{state: 'FAILED'}, {state: 'SUCCESS'}]), 30000);
  assert.equal(pollDelay([]), 30000);
});

/* Read-only polling does not extend sessions. Writes are never replayed after MFA. */
(() => {
  'use strict';

  const actions = {
    create: 'Створення резервної копії',
    verify: 'Перевірка резервної копії',
    emergency: 'Створення нової версії Excel',
    usb: 'Копіювання аварійного архіву на USB',
    statistics: 'Оновлення вимірювань сховища',
  };
  const errors = {
    EMERGENCY_GENERATION_FAILED: 'Не вдалося сформувати Excel. Перевірте журнал резервування.',
    USB_COPY_FAILED: 'Не вдалося скопіювати архів. Перевірте, чи флешка підключена до сервера.',
    STORAGE_NTFS_ACL_REQUIRED: 'Перевірте дозволи NTFS на каталоги архіву та носій.',
    USB_BITLOCKER_REQUIRED: 'Підключіть дозволену флешку з розблокованим BitLocker.',
    USB_VOLUME_CHANGED_OR_NOT_ALLOWED: 'Носій змінився або його не дозволено. Підключіть і виберіть потрібну флешку.',
    USB_INSUFFICIENT_SPACE: 'На флешці бракує вільного місця.',
    BACKUP_AUTHORIZATION_EXPIRED: 'Дозвіл на завдання втратив чинність. Перевірте Project2-Backup і повторіть дію.',
    BACKUP_DRILL_FAILED: 'Тестове відновлення завершилося помилкою. Перевірте журнал резервування.',
    BACKUP_DRILL_APPROVAL_REQUIRED: 'Master має надати серверний дозвіл на тестове відновлення.',
    EMERGENCY_QUOTA_EXCEEDED: 'Досягнуто ліміту місця для аварійного архіву.',
    MFA_REAUTH_REQUIRED: 'Підтвердьте особу в діалозі. Потім натисніть кнопку операції ще раз.',
    BACKUP_JOB_FAILED: 'Не вдалося завершити завдання. Перевірте журнал резервування.',
  };
  const expired = 'Прострочено — worker не підхопив завдання за 5 хв (перевірте, що завдання Project2-Backup увімкнене)';
  const errorText = code => Object.hasOwn(errors, code) ? errors[code] : code;
  const isActive = job => job.state === 'QUEUED' || job.state === 'RUNNING';
  const pollDelay = jobs => jobs.some(isActive) ? 3000 : 30000;

  function jobPresentation(job, now = Date.now()) {
    if (job.state === 'RUNNING') return {tone: 'info', text: 'Виконується'};
    if (job.state === 'SUCCESS') return {tone: 'success', text: 'Готово'};
    const deadline = Date.parse(job.authorization_expires_at);
    const timedOut = deadline < now;
    if (job.state === 'QUEUED') {
      return timedOut ? {tone: 'warning', text: expired}
        : {tone: 'info', text: 'У черзі — очікує worker (до 1 хв)'};
    }
    if (job.state === 'FAILED') {
      if (job.code === 'BACKUP_AUTHORIZATION_EXPIRED' && timedOut) return {tone: 'warning', text: expired};
      return {tone: 'danger', text: 'Помилка: ' + errorText(job.code || 'BACKUP_JOB_FAILED')};
    }
    return {tone: 'secondary', text: job.state};
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {jobPresentation, pollDelay, errorText};
    return;
  }

  const root = document.querySelector('[data-backup-panel]');
  if (!root) return;
  const get = selector => root.querySelector(selector);
  const message = get('[data-backup-message]');
  const emergencyAccepted = get('[data-emergency-accepted]');
  const list = get('[data-backup-list]');
  const select = get('[data-usb-volume]');
  const actionsBySelector = {
    create: '[data-backup-create]', emergency: '[data-emergency-create]',
    usb: '[data-usb-open]', statistics: '[data-storage-refresh]',
  };
  const labels = {
    VERIFIED: 'Цілісність підтверджено', SUCCESS: 'Успішно', FAILED: 'Помилка',
    NOT_RUN: 'Ще не виконано', NOT_CONFIGURED: 'Не налаштовано', CORRUPT: 'Пошкоджено',
    MISSING: 'Відсутнє', PRUNED: 'Видалено', QUEUED: 'У черзі', RUNNING: 'Виконується',
  };
  const el = (tag, text, className = '') => {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const size = value => value == null ? '—' : (value / 1024 ** 2).toLocaleString('uk-UA', {maximumFractionDigits: 2}) + ' МіБ';
  const actionButtons = Object.entries(actionsBySelector).map(([type, selector]) => [type, get(selector)]);
  const notices = new Map();
  const watching = new Map();
  const submitting = new Set();
  let state = JSON.parse(get('[data-backup-state]').textContent);
  let clockOffset = 0;
  let revision = 0;
  let refresh;
  let timer;
  let backupsSignature;
  let mfaAction;

  function syncClock() {
    const server = Date.parse(state.server_at);
    if (Number.isFinite(server)) clockOffset = server - Date.now();
  }

  const guide = get('[data-backup-guide]');
  const guideKey = 'project2:backup-guide-collapsed';
  try { guide.open = localStorage.getItem(guideKey) !== '1'; } catch {}
  guide.addEventListener('toggle', () => {
    try { localStorage.setItem(guideKey, guide.open ? '0' : '1'); } catch {}
  });

  async function request(url, body) {
    const response = await fetch(url, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : '';
      const mfa = response.status === 403 && detail.startsWith('MFA_REAUTH_REQUIRED');
      const error = Error(mfa ? errorText('MFA_REAUTH_REQUIRED') : detail || 'Не вдалося виконати дію.');
      error.mfa = mfa;
      throw error;
    }
    return data;
  }

  function setNotice(key, text = '') {
    if (text) notices.set(key, text);
    else notices.delete(key);
    renderNotices();
  }

  function renderNotices() {
    root.querySelectorAll('[data-job-notice]').forEach(node => {
      node.textContent = notices.get(node.dataset.jobNotice) || '';
      node.hidden = !node.textContent;
    });
  }

  function renderCards(node, jobs) {
    const cards = jobs.map(job => ({
      name: actions[job.operation] || job.operation,
      at: job.at_kyiv,
      ...jobPresentation(job, Date.now() + clockOffset),
    }));
    const signature = JSON.stringify(cards);
    if (node.dataset.signature === signature) return;
    node.dataset.signature = signature;
    node.replaceChildren(...cards.map(card => {
      const element = el('article', '', 'border rounded p-2');
      element.append(el('strong', card.name), el('div', card.at || '—', 'text-body-secondary small'),
        el('span', card.text, 'badge text-bg-' + card.tone + ' text-start text-wrap'));
      return element;
    }));
  }

  function renderSummary() {
    const full = state.last_full;
    const excel = state.emergency;
    const usb = state.last_usb;
    get('[data-backup-last]').textContent = full
      ? `${full.snapshot_at_kyiv} · ${size(full.size)} · Тестове відновлення успішне: ${full.drill === 'SUCCESS' ? 'так' : 'ні'}`
      : 'Готових копій ще немає';
    get('[data-emergency-last]').textContent = excel
      ? `${excel.at_kyiv} · Книги: ${size(excel.size)} · Файли документів і фото: ${excel.file_count}`
      : 'Готових версій ще немає';
    get('[data-usb-last]').textContent = usb
      ? `${usb.at_kyiv} · Носій: ${usb.label || 'мітка невідома'} · Excel: ${usb.excel_at_kyiv || 'час невідомий'} · Скопійовано файлів: ${usb.files ?? '—'}`
      : 'Копій на USB ще немає';
    get('[data-usb-outdated]').hidden = !usb?.outdated;
    const drill = state.last_drill;
    get('[data-backup-drill]').textContent = drill
      ? drill.at_kyiv + ' · ' + Number(drill.details.restore_seconds).toFixed(2) + ' с'
      : state.drill_configured ? 'Очікує виконання' : 'Не налаштовано або ще не виконувалося';
    const warning = get('[data-backup-warning]');
    warning.hidden = state.configured && !state.rpo_overdue && !state.external_overdue && !state.statistics?.low_space;
    warning.textContent = state.configured ? (state.statistics?.low_space
      ? 'Недостатньо вільного місця. Перевірте сховища.'
      : 'Немає копії з успішним тестовим відновленням за останню годину або прострочено зовнішню репліку. Перевірте worker і планувальник.')
      : state.message;
    get('[data-backup-failure]').textContent = state.last_failure
      ? state.last_failure.at_kyiv + ' · ' + (errorText(state.last_failure.code) || 'Помилка') : 'Не зафіксовано';
    get('[data-backup-next]').textContent = state.next_at_kyiv || 'Не налаштовано';
    get('[data-backup-external]').textContent = state.external_configured
      ? state.external_available ? 'Доступне' : 'Недоступне' : 'Не налаштовано';
  }

  function renderBackups() {
    const signature = JSON.stringify([state.can_run, state.backups]);
    if (signature === backupsSignature) return;
    backupsSignature = signature;
    list.replaceChildren();
    for (const backup of state.backups) {
      const row = el('tr', '');
      const type = backup.schedule === 'daily' ? 'Щоденна повна'
        : backup.schedule === 'hourly' ? 'Щогодинна повна' : backup.kind === 'full' ? 'Повна' : 'Самодостатня точка';
      for (const value of [backup.snapshot_at_kyiv, type, size(backup.size), labels[backup.integrity] || backup.integrity,
        backup.drill === 'SUCCESS' ? 'Тестове відновлення успішне' : labels[backup.drill || 'NOT_RUN'],
        labels[backup.external] || backup.external]) row.append(el('td', value));
      const cell = el('td', '');
      if (state.can_run && backup.integrity !== 'PRUNED') {
        const button = el('button', 'Перевірити', 'btn btn-sm btn-outline-primary');
        button.type = 'button';
        button.dataset.backupVerify = backup.id;
        button.addEventListener('click', () => run('verify', '/verify/' + encodeURIComponent(backup.id), {}, 'verify-' + backup.id));
        const notice = el('p', '', 'alert alert-warning mt-2 mb-0');
        notice.dataset.jobNotice = 'verify-' + backup.id;
        notice.setAttribute('role', 'status');
        cell.append(button, notice);
      }
      row.append(cell);
      list.append(row);
    }
  }

  function renderStatistics() {
    const node = get('[data-storage-statistics]');
    const s = state.statistics;
    if (!s) {
      node.replaceChildren(el('dd', 'Вимірювань ще немає.'));
      return;
    }
    const fields = [
      ['Виміряно (Київ)', s.at_kyiv], ['PostgreSQL', size(s.database_size)],
      ['Повні копії', size(s.backups.size) + ' · ' + s.backups.count + ' копій'],
      ['Excel', size(s.excel.size) + ' · ' + s.excel.files + ' файлів'],
      ['Фото та документи', size(s.documents.size) + ' · ' + s.documents.files + ' файлів'],
      ['Приріст від базового вимірювання', size(s.growth_7_days)],
      ['Вільно: копії / Excel / документи', [s.backups.free, s.excel.free, s.documents.free].map(size).join(' / ')],
      ['Остання успішна операція', s.last_success_kyiv || '—'], ['Остання невдала операція', s.last_failure_kyiv || '—'],
    ];
    node.replaceChildren(...fields.flatMap(([label, value]) => [el('dt', label, 'col-sm-5'), el('dd', value, 'col-sm-7')]));
  }

  function render() {
    const active = state.active_jobs || [];
    const latest = new Map([...state.jobs, ...(state.watched_jobs || []), ...active].map(job => [job.id, job]));
    for (const [type, job] of watching) if (latest.has(job.id)) watching.set(type, latest.get(job.id));
    const current = new Map([...active, ...watching.values()].map(job => [job.id, job]));
    get('[data-backup-current-section]').hidden = !current.size;
    renderCards(get('[data-backup-current]'), [...current.values()]);
    renderCards(get('[data-backup-jobs]'), state.jobs.slice(0, 5));
    if (!state.jobs.length) get('[data-backup-jobs]').textContent = 'Завдань ще немає.';

    renderSummary();
    renderBackups();
    renderStatistics();
    const busy = type => submitting.has(type) || active.some(job => job.operation === type);
    function setButton(button, type) {
      button.dataset.label ||= button.textContent;
      button.disabled = busy(type);
      button.textContent = button.disabled ? 'Виконується…' : button.dataset.label;
    }
    for (const [type, button] of actionButtons) {
      button.hidden = ['usb', 'emergency'].includes(type) ? !state.can_export : !state.can_run;
      setButton(button, type);
    }
    for (const button of list.querySelectorAll('[data-backup-verify]')) setButton(button, 'verify');
    const confirm = get('[data-usb-confirm]');
    setButton(confirm, 'usb');
    confirm.disabled ||= !state.can_export || !select.value || select.selectedOptions[0]?.disabled;
    renderNotices();

    get('[data-backup-events]').replaceChildren(...state.events.slice(-10).reverse().map(event => el('p',
      `${event.at_kyiv} · ${event.actor_user_id ? 'Користувач ID ' + event.actor_user_id : 'Серверна операція'} · ${event.operation} · ${labels[event.result] || event.result}` +
      (event.code ? ' · ' + errorText(event.code) : '') +
      (event.details?.files != null ? ` · ${event.details.files} файлів · ${size(event.details.size)}` : ''))));
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => document.hidden ? schedule() : load(), pollDelay(state.active_jobs || []));
  }

  function load() {
    if (refresh) return refresh;
    const startedAt = revision;
    const query = new URLSearchParams();
    for (const job of watching.values()) if (isActive(job)) query.append('job', job.id);
    refresh = request('/admin/backups/data' + (query.size ? '?' + query : '')).then(data => {
      if (startedAt !== revision) return;
      state = data;
      syncClock();
      render();
    }).catch(error => { message.textContent = error.message; }).finally(() => {
      refresh = null;
      schedule();
    });
    return refresh;
  }

  async function run(type, path, body = {}, key = type) {
    if (submitting.has(type)) return;
    submitting.add(type);
    if (type === 'emergency') emergencyAccepted.textContent = '';
    setNotice(key);
    render();
    try {
      const job = await request('/admin/backups' + path, body);
      revision++;
      watching.set(type, job);
      state.jobs = [job, ...state.jobs.filter(row => row.id !== job.id)]
        .sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).slice(0, 5);
      state.active_jobs = (state.active_jobs || []).filter(row => row.id !== job.id);
      if (isActive(job)) state.active_jobs.push(job);
      if (type === 'emergency') {
        emergencyAccepted.textContent = 'Завдання створення нової версії Excel прийнято обробку.';
      } else {
        message.textContent = 'Завдання прийнято worker.';
      }
    } catch (error) {
      if (error.mfa) mfaAction = key;
      setNotice(key, error.message);
    } finally {
      submitting.delete(type);
      render();
      schedule();
    }
  }

  root.addEventListener('project2:mfa-confirmed', () => {
    if (mfaAction) setNotice(mfaAction, root.dataset.mfaReauthConfirmed);
    mfaAction = null;
  });
  get('[data-backup-create]').addEventListener('click', () => run('create', '/create'));
  get('[data-backup-refresh]').addEventListener('click', load);
  get('[data-emergency-create]').addEventListener('click', () => run('emergency', '/emergency'));
  get('[data-storage-refresh]').addEventListener('click', () => run('statistics', '/statistics'));
  get('[data-usb-open]').addEventListener('click', async () => {
    setNotice('usb');
    try {
      const volumes = await request('/admin/backups/volumes');
      const selected = select.value;
      select.replaceChildren();
      for (const volume of volumes) {
        const option = el('option', `${volume.label || 'USB'} · ${volume.root} · вільно ${size(volume.free)}${volume.eligible ? '' : ' · BitLocker недоступний'}`);
        option.value = volume.id;
        option.disabled = !volume.eligible;
        select.append(option);
      }
      if (volumes.some(volume => volume.id === selected && volume.eligible)) select.value = selected;
      else select.selectedIndex = volumes.findIndex(volume => volume.eligible);
      get('[data-usb-picker]').hidden = false;
      if (!volumes.length) setNotice('usb', 'Дозволених USB на сервері не знайдено.');
      render();
    } catch (error) { setNotice('usb', error.message); }
  });
  select.addEventListener('change', render);
  get('[data-usb-confirm]').addEventListener('click', () => {
    if (select.value) run('usb', '/usb', {volume_id: select.value});
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  syncClock();
  render();
  schedule();
})();

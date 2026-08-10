/* global document, apiFetch, Intl, S, goto */
// Config step: hostname/timezone/locale/keymap/user account.

function initConfig() {
  const sel = document.getElementById('sel-tz');
  if (sel.options.length === 0) {
    apiFetch('/api/timezones').then(r=>r.json()).then(tzs => {
      const local = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
      (tzs.length ? tzs : ['UTC']).forEach(tz => {
        const opt = document.createElement('option');
        opt.value = tz; opt.textContent = tz;
        if (tz === local) opt.selected = true;
        sel.appendChild(opt);
      });
    }).catch(() => {
      const opt = document.createElement('option');
      opt.value = 'UTC'; opt.textContent = 'UTC';
      opt.selected = true;
      sel.appendChild(opt);
    });
  }
  const populate = (id, endpoint, fallback, preferred) => {
    const target = document.getElementById(id);
    if (target.options.length) return;
    apiFetch(endpoint).then(r => r.json()).then(values => {
      (values.length ? values : [fallback]).forEach(value => {
        const opt = document.createElement('option');
        opt.value = value; opt.textContent = value; opt.selected = value === preferred;
        target.appendChild(opt);
      });
    }).catch(() => {
      const opt = document.createElement('option');
      opt.value = fallback; opt.textContent = fallback; opt.selected = true;
      target.appendChild(opt);
    });
  };
  populate('sel-locale', '/api/locales', 'en_US.UTF-8', S.locale);
  populate('sel-keymap', '/api/keymaps', 'us', S.keymap);
}

// Called from index.html's inline onclick handler, not referenced within this file.
// eslint-disable-next-line no-unused-vars
function saveConfig() {
  const hostname = document.getElementById('inp-hostname').value.trim();
  const username = document.getElementById('inp-username').value.trim();
  const pw1      = document.getElementById('inp-password').value;
  const pw2      = document.getElementById('inp-password2').value;
  const errEl    = document.getElementById('user-error');
  errEl.textContent = '';

  // eslint-disable-next-line -- bounded, linear-time expression, safe from ReDoS
  if (!/^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/.test(hostname)) { // nosemgrep -- bounded, linear-time expression
    errEl.textContent = 'Hostname must contain only letters, digits, and hyphens.'; return;
  }
  if (!/^[a-z_][a-z0-9_-]{0,30}$/.test(username)) {
    errEl.textContent = 'Username must start with a letter, use only lowercase letters/digits/hyphens.'; return;
  }
  if (pw1.length < 1) { errEl.textContent = 'Password is required.'; return; }
  if (pw1 !== pw2)    { errEl.textContent = 'Passwords do not match.'; return; }

  S.hostname = hostname;
  S.timezone = document.getElementById('sel-tz').value;
  S.locale = document.getElementById('sel-locale').value;
  S.keymap = document.getElementById('sel-keymap').value;
  S.username = username;
  S.password = pw1;
  goto('review');
}

// Referenced by an inline event attribute in index.html.
void [saveConfig];

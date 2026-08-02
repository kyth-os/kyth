/* global document, fetch, Headers */
const S = globalThis.KythInstallerState;
let SESSION_TOKEN = 'SESSION_TOKEN_PLACEHOLDER';

// Build DOM nodes directly instead of assembling HTML strings — keeps
// backend-provided values (disk models, labels, …) out of markup entirely.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k === 'style') node.style.cssText = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) node.append(child.nodeType ? child : String(child));
  }
  return node;
}

function apiFetch(url, opts={}) {
  if (typeof url !== 'string' || !url.startsWith('/api/')) {
    throw new TypeError('API requests must use a same-origin /api/ route');
  }
  const options = {...opts, credentials:'same-origin'};
  const headers = new Headers(options.headers || {});
  if (SESSION_TOKEN) headers.set('X-Kyth-Session-Token', SESSION_TOKEN);
  options.headers = headers;
  return fetch(url, options); // nosemgrep -- constrained to a same-origin API route above
}

function postRequest(url, body) {
  return apiFetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
}

function postJSON(url, body) {
  return postRequest(url, body).then(response => response.json());
}

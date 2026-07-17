import os
import re
import subprocess
from urllib.parse import parse_qs, urlencode, unquote, urlparse
from urllib.request import Request, urlopen

# __KYTH_GENERATED_IMPORTS__
from .core_base import _restyle
from .services.vpn import (
    VPN_OS_OPTIONS as _VPN_OS_OPTIONS,
    VPN_PROTOCOLS as _VPN_PROTOCOLS,
    VpnConnectWorker as _VpnConnectWorker,
    _GP_PRELOGIN_IFACE_RE,
    _GP_SAML_FIELDS,
    _load_vpn_config,
    _parse_gp_saml_cookie,
    _redact_vpn_log_line,
    _save_vpn_config,
    _vpn_line_is_connected,
)
from .qt import (  # noqa: E501
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QTextEdit, QTimer, QUrl, QVBoxLayout, QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestJob, QWebEngineUrlSchemeHandler, QWebEngineView, Signal, _WEBENGINE_AVAILABLE,
)
from .widgets import (  # noqa: E501
    Page, _make_card, _set_log_panel,
)

# ── VPN page ──────────────────────────────────────────────────────────────────
if _WEBENGINE_AVAILABLE:
    class _GpCallbackHandler(QWebEngineUrlSchemeHandler):
        """Catches GlobalProtect callback URLs regardless of how they're triggered."""
        url_received = Signal(str)

        def requestStarted(self, request: QWebEngineUrlRequestJob) -> None:
            url = request.requestUrl().toString()
            try:
                body_dev = request.requestBody()
                if body_dev is not None:
                    raw = body_dev.readAll()
                    if raw:
                        body_str = bytes(raw).decode("utf-8", errors="replace")
                        print("[SAML dbg] callback POST body received")
                        sep = "&" if "?" in url else "?"
                        url = url + sep + body_str
            except Exception as exc:
                print(f"[SAML dbg] requestBody read error: {exc}")
            if url.startswith("gc://saml-acs"):
                print("[SAML dbg] scheme handler url: gc://saml-acs?<redacted>")
            else:
                print(f"[SAML dbg] scheme handler url: {url[:200]}")
            self.url_received.emit(url)
            request.fail(QWebEngineUrlRequestJob.Error.RequestAborted)

    class _SamlWebPage(QWebEnginePage):
        callback_received = Signal(str)
        prelogin_result = Signal(str)

        def __init__(self, profile, parent=None):
            super().__init__(profile, parent)

        def javaScriptConsoleMessage(self, level, message, line, source):
            print(f"[JS console] {message} ({source}:{line})")
            if message.startswith("[GP-PRELOGIN-COOKIE] "):
                self.prelogin_result.emit(message[len("[GP-PRELOGIN-COOKIE] "):])
            elif message.startswith(("[GP-PRELOGIN-RAW] ", "[GP-PRELOGIN-ERROR] ")):
                self.prelogin_result.emit("")

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            url_str = url.toString()
            if url_str.startswith("globalprotectcallback:") or url_str.startswith("gc:"):
                self.callback_received.emit(url_str)
                return False
            return True

    _GP_AUTH_COOKIES = _GP_SAML_FIELDS

    class SamlBrowserDialog(QDialog):
        cookie_ready = Signal(str)

        def __init__(self, saml_url: str, parent=None):
            super().__init__(parent)
            self.setWindowTitle("VPN — SAML Authentication")
            self.resize(960, 720)
            self.setMinimumSize(720, 560)
            self.setModal(True)
            self.setObjectName("saml-dialog")
            self.setStyleSheet("""
QDialog#saml-dialog {
    background: #111418;
}
QFrame#saml-header {
    background: #171b21;
    border: 1px solid #2a313a;
    border-radius: 8px;
}
QLabel#saml-title {
    color: #f1f5f9;
    font-size: 16px;
    font-weight: 700;
}
QLabel#saml-info {
    color: #aeb8c5;
    font-size: 12px;
}
QFrame#saml-browser-frame {
    background: #ffffff;
    border: 1px solid #303844;
    border-radius: 8px;
}
QLabel#saml-status {
    color: #9fb0c2;
    font-size: 12px;
}
QPushButton#saml-cancel {
    background: #232a33;
    border: 1px solid #3a4452;
    border-radius: 6px;
    color: #edf2f7;
    padding: 7px 18px;
}
QPushButton#saml-cancel:hover {
    background: #2d3642;
}
QPushButton#saml-cancel:pressed {
    background: #1d232b;
}
""")
            self._done = False
            self._all_cookies: dict[str, str] = {}

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 14, 14, 12)
            layout.setSpacing(10)

            header = QFrame(self)
            header.setObjectName("saml-header")
            header_layout = QVBoxLayout(header)
            header_layout.setContentsMargins(14, 12, 14, 12)
            header_layout.setSpacing(4)

            title = QLabel("VPN sign-in", header)
            title.setObjectName("saml-title")
            header_layout.addWidget(title)

            self._info = QLabel("Complete your organization sign-in to continue the VPN connection.", header)
            self._info.setObjectName("saml-info")
            self._info.setWordWrap(True)
            header_layout.addWidget(self._info)
            layout.addWidget(header)

            # Named persistent profile: keeps the IdP session cookies so the
            # gateway SAML leg (and future reconnects) can complete without
            # re-entering credentials. An unnamed profile is off-the-record and
            # would force a full sign-in for every leg.
            from pathlib import Path
            _store = Path.home() / ".local" / "share" / "kyth-welcome" / "webengine"
            _store.mkdir(parents=True, exist_ok=True)
            self._profile = QWebEngineProfile("kyth-vpn-saml", self)
            self._profile.setPersistentStoragePath(str(_store))
            self._profile.setCachePath(str(_store / "cache"))
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            from .qt import QWebEngineScript
            _intercept = QWebEngineScript()
            _intercept.setName("gp-submit-intercept")
            _intercept.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            _intercept.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            _intercept.setRunsOnSubFrames(True)
            _intercept.setSourceCode("""
(function(){
    function submitToKyth(form) {
        var action = form.action || '';
        if (action.indexOf('/SAML20/SP/ACS') < 0) return false;
        var fd;
        try { fd = new FormData(form); } catch(e) { return false; }
        if (!fd.get('SAMLResponse')) return false;
        var params = new URLSearchParams();
        for (var pair of fd.entries()) params.append(pair[0], pair[1]);
        window.location.href = 'gc://saml-acs?url=' + encodeURIComponent(action) +
            '&body=' + encodeURIComponent(params.toString());
        return true;
    }
    var _orig = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function() {
        var fields=[];
        try{ var fd=new FormData(this); for(var[k,v] of fd) fields.push(String(k)); }catch(e){}
        console.log('[GP-FORM-SUBMIT] action='+this.action+' method='+this.method+' fields='+JSON.stringify(fields));
        if (submitToKyth(this)) return;
        _orig.call(this);
    };
    document.addEventListener('submit', function(e){
        var f=e.target;
        console.log('[GP-FORM-EVENT] action='+f.action+' method='+f.method);
        if (submitToKyth(f)) {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);
})();
""")
            self._profile.scripts().insert(_intercept)
            self._cb_handler = _GpCallbackHandler(self)
            self._cb_handler.url_received.connect(self._on_callback)
            self._profile.installUrlSchemeHandler(b"globalprotectcallback", self._cb_handler)
            self._profile.installUrlSchemeHandler(b"gc", self._cb_handler)
            self._page = _SamlWebPage(self._profile, self._profile)
            self._page.callback_received.connect(self._on_callback)
            self._page.prelogin_result.connect(self._on_prelogin_result)

            browser_frame = QFrame(self)
            browser_frame.setObjectName("saml-browser-frame")
            browser_layout = QVBoxLayout(browser_frame)
            browser_layout.setContentsMargins(1, 1, 1, 1)
            browser_layout.setSpacing(0)
            self._view = QWebEngineView(self)
            self._view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._view.setPage(self._page)
            browser_layout.addWidget(self._view)
            layout.addWidget(browser_frame, 1)

            footer = QHBoxLayout()
            footer.setContentsMargins(2, 0, 2, 0)
            footer.setSpacing(10)
            self._status_msg = QLabel("Waiting for sign-in")
            self._status_msg.setObjectName("saml-status")
            footer.addWidget(self._status_msg)
            footer.addStretch(1)
            cancel = QPushButton("Cancel")
            cancel.setObjectName("saml-cancel")
            cancel.clicked.connect(self.reject)
            footer.addWidget(cancel)
            layout.addLayout(footer)

            cookie_store = self._profile.cookieStore()
            cookie_store.loadAllCookies()
            cookie_store.cookieAdded.connect(self._on_cookie_added)
            self._cookie_store = cookie_store
            self._view.loadFinished.connect(self._on_load_finished)
            self._view.urlChanged.connect(self._on_url_changed)
            self._view.load(QUrl(saml_url))

        _GP_TOKEN_JS = """
(function() {
    var names = ['preloginuserauthcookie','portal-userauthcookie','cas','prelogin-cookie'];
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
        var c = cookies[i].trim();
        var sep = c.indexOf('=');
        if (sep < 0) continue;
        var n = c.substring(0, sep).trim().toLowerCase();
        if (names.indexOf(n) >= 0) return n + '=' + c.substring(sep + 1);
    }
    var inputs = document.querySelectorAll('input');
    for (var i = 0; i < inputs.length; i++) {
        var n = (inputs[i].name || '').toLowerCase();
        if (names.indexOf(n) >= 0 && inputs[i].value)
            return n + '=' + inputs[i].value;
    }
    var text = (document.body && document.body.innerText) ? document.body.innerText : '';
    if (text) {
        for (var k = 0; k < names.length; k++) {
            var re = new RegExp('<' + names[k] + '>([^<]+)</' + names[k] + '>', 'i');
            var m = text.match(re);
            if (m && m[1]) return names[k] + '=' + m[1].trim();
        }
    }
    var forms = document.forms;
    for (var i = 0; i < forms.length; i++) {
        var action = (forms[i].action || '').toLowerCase();
        if (action.indexOf('globalprotectcallback:') === 0 || action.indexOf('gc:') === 0) {
            var fd = new FormData(forms[i]);
            for (var j = 0; j < names.length; j++) {
                var v = fd.get(names[j]);
                if (v) return names[j] + '=' + v;
            }
        }
    }
    return '';
})()
"""

        _FORM_DEBUG_JS = """
(function() {
    var parts = [];
    for (var i = 0; i < document.forms.length; i++) {
        var f = document.forms[i];
        var fields = [];
        for (var j = 0; j < f.elements.length; j++) {
            var el = f.elements[j];
            fields.push(el.name + ':' + el.type);
        }
        parts.push('form['+i+'] action='+f.action+' method='+f.method+' fields=['+fields.join(',')+']');
    }
    var metas = document.querySelectorAll('meta[http-equiv]');
    for (var i = 0; i < metas.length; i++)
        parts.push('meta http-equiv='+metas[i].getAttribute('http-equiv')+' content='+metas[i].content.substring(0,60));
    parts.push('scripts='+document.scripts.length);
    parts.push('location='+window.location.href.substring(0,80));
    return parts.join(' | ') || '(no forms)';
})()
"""

        _PRELOGIN_FETCH_JS = """
(function(){
    var params = new URLSearchParams({
        tmp:'tmp','kerberos-support':'yes','ipv6-support':'yes',
        clientos:'Windows',clientgpversion:'5.1.5.0',hostname:''
    });
    fetch('/global-protect/prelogin.esp',{
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:params.toString(),
        credentials:'include'
    }).then(function(r){return r.text();}).then(function(text){
        var parser=new DOMParser();
        var doc=parser.parseFromString(text,'application/xml');
        var tags=['prelogin-cookie','portal-userauthcookie','cas','preloginuserauthcookie'];
        for(var i=0;i<tags.length;i++){
            var el=doc.querySelector(tags[i]);
            if(el&&el.textContent.trim()){
                console.log('[GP-PRELOGIN-COOKIE] '+tags[i]+'='+el.textContent.trim());
                return;
            }
        }
        console.log('[GP-PRELOGIN-RAW] no auth cookie in prelogin XML');
    }).catch(function(e){console.log('[GP-PRELOGIN-ERROR] '+String(e));});
})();
"""

        def _on_url_changed(self, url: QUrl) -> None:
            url_str = url.toString()
            print(f"[SAML dbg] urlChanged: {url_str[:120]}")
            if url_str.startswith("globalprotectcallback:") or url_str.startswith("gc:"):
                self._on_callback(url_str)

        def _on_load_finished(self, ok: bool) -> None:
            try:
                if self._done:
                    return
                current_url = self._page.url().toString()
                print(f"[SAML dbg] loadFinished ok={ok} url={current_url[:120]}")
                if not ok:
                    return
                self._page.runJavaScript(self._GP_TOKEN_JS, self._on_js_token)
                if current_url.startswith("globalprotectcallback:") or current_url.startswith("gc:"):
                    self._on_callback(current_url)
                    return
                _ms = ("microsoftonline.com", "microsoft.com", "live.com", "msftauth.net")
                if not any(h in current_url for h in _ms):
                    _url_snap = current_url
                    self._page.runJavaScript(
                        self._FORM_DEBUG_JS,
                        lambda r: self._on_portal_page_structure(str(r or ""), _url_snap),
                    )
                self._page.runJavaScript("document.title", self._on_page_title)
            except Exception as e:
                print("[SAML load_finished error]", e)

        def _on_page_title(self, title) -> None:
            title_str = str(title or "")
            print(f"[SAML dbg] page title: {title_str!r}")
            if self._done:
                return
            if any(kw in title_str.lower() for kw in ("successful", "success", "complete", "logged in")):
                print("[SAML dbg] success page detected — checking collected cookies in 5s")
                QTimer.singleShot(5000, self._fallback_cookie_check)

        def _on_portal_page_structure(self, result: str, url: str) -> None:
            print(f"[SAML dbg] page structure: {result}")
            if self._done:
                return
            if "scripts=0" in result and "form[" not in result:
                print("[SAML dbg] static portal page — trying session cookies in 2s")
                QTimer.singleShot(2000, self._try_portal_session_cookie)

        def _try_portal_session_cookie(self) -> None:
            if self._done:
                return
            print(f"[SAML dbg] session cookie attempt — cookies seen: {list(self._all_cookies.keys())}")
            self._status_msg.setText("Completing VPN handoff")
            for name in _GP_AUTH_COOKIES:
                if name in self._all_cookies:
                    print(f"[SAML dbg] using cookie: {name}")
                    self._emit_cookie(f"{name}={self._all_cookies[name]}")
                    return
            if "SESSID" not in self._all_cookies:
                self._info.setText(
                    "Portal login complete but no VPN token found. "
                    "Cookies: " + ", ".join(self._all_cookies.keys())
                )
                self._status_msg.setText("VPN token not received")
                return
            print("[SAML dbg] exchanging SESSID for prelogin-cookie via portal API")
            self._page.runJavaScript(self._PRELOGIN_FETCH_JS)

        def _on_prelogin_result(self, cookie_str: str) -> None:
            if self._done:
                return
            if cookie_str:
                print("[SAML dbg] prelogin exchange succeeded")
                self._emit_cookie(cookie_str)
            else:
                print("[SAML dbg] prelogin exchange did not return a GP auth token")
                self._info.setText(
                    "Portal login completed, but the VPN token was not received. "
                    "Leave this window open and check the terminal for '[SAML dbg]' lines."
                )
                self._status_msg.setText("VPN token not received")

        def _fallback_cookie_check(self) -> None:
            if self._done:
                return
            print(f"[SAML dbg] fallback cookie check — collected: {list(self._all_cookies.keys())}")
            for name in _GP_AUTH_COOKIES:
                if name in self._all_cookies:
                    print(f"[SAML dbg] fallback found cookie: {name}")
                    self._emit_cookie(f"{name}={self._all_cookies[name]}")
                    return
            self._info.setText(
                "Authentication appeared successful but the VPN token was not received. "
                "Check the log for '[SAML dbg]' lines and report the cookie names seen."
            )
            self._status_msg.setText("VPN token not received")

        def _on_js_token(self, result) -> None:
            try:
                if self._done or not result:
                    return
                print("[SAML dbg] JS token found")
                self._emit_cookie(result)
            except Exception as e:
                print("[SAML js_token error]", e)

        def _on_cookie_added(self, cookie) -> None:
            try:
                name = cookie.name().data().decode("utf-8", errors="replace")
                value = cookie.value().data().decode("utf-8", errors="replace")
                print(f"[SAML dbg] cookie: {name}=<redacted>")
                self._all_cookies[name] = value
                if self._done:
                    return
                if name in _GP_AUTH_COOKIES:
                    print(f"[SAML dbg] GP auth cookie matched: {name}")
                    self._emit_cookie(f"{name}={value}")
            except Exception as e:
                print("[SAML cookie_added error]", e)

        def _on_callback(self, url: str) -> None:
            if self._done:
                return
            parsed = urlparse(url)
            if parsed.scheme == "gc" and parsed.netloc == "saml-acs":
                print("[SAML dbg] callback URL: gc://saml-acs?<redacted>")
            else:
                print(f"[SAML dbg] callback URL: {url[:120]}")
            if parsed.scheme == "gc" and parsed.netloc == "saml-acs":
                params = parse_qs(parsed.query, keep_blank_values=True)
                self._on_saml_acs_form(
                    params.get("url", [""])[0],
                    params.get("body", [""])[0],
                )
                return
            qs = parsed.query if parsed.query else parsed.path.lstrip('/?')
            params = parse_qs(unquote(qs))
            print(f"[SAML dbg] callback params: {list(params.keys())}")
            cookie_str = ""
            for name in _GP_SAML_FIELDS:
                if name in params:
                    cookie_str = f"{name}={params[name][0]}"
                    break
            if cookie_str:
                self._emit_cookie(cookie_str)

        def _on_saml_acs_form(self, action_url: str, body: str) -> None:
            if self._done or not action_url or not body:
                return
            print("[SAML dbg] captured SAML ACS form; replaying to read GP headers")
            self._status_msg.setText("Completing VPN handoff")
            try:
                req = Request(
                    action_url,
                    data=body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": "PAN GlobalProtect",
                    },
                    method="POST",
                )
                with urlopen(req, timeout=30) as resp:
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    text = resp.read().decode("utf-8", errors="replace")
            except Exception as exc:
                print(f"[SAML dbg] ACS replay failed: {exc}")
                self._info.setText("Could not replay the SAML response to the VPN portal.")
                self._status_msg.setText("VPN handoff failed")
                return

            print(f"[SAML dbg] ACS replay headers: {sorted(headers.keys())}")
            for name in ("prelogin-cookie", "portal-userauthcookie", "cas", "preloginuserauthcookie"):
                if headers.get(name):
                    print(f"[SAML dbg] ACS replay found {name} and saml-username")
                    self._emit_cookie(urlencode({
                        name: headers[name],
                        "saml-username": headers.get("saml-username", ""),
                    }))
                    return

            for name in ("prelogin-cookie", "portal-userauthcookie", "cas", "preloginuserauthcookie"):
                m = re.search(rf"<{re.escape(name)}>([^<]+)</{re.escape(name)}>", text, re.I)
                if m:
                    user_match = re.search(r"<saml-username>([^<]+)</saml-username>", text, re.I)
                    print(f"[SAML dbg] ACS body found {name}")
                    self._emit_cookie(urlencode({
                        name: m.group(1).strip(),
                        "saml-username": user_match.group(1).strip() if user_match else "",
                    }))
                    return

            print("[SAML dbg] ACS replay did not include a GP auth token")
            self._info.setText("SAML completed, but the VPN portal did not return a GP auth token.")
            self._status_msg.setText("VPN token not received")

        def _teardown_webengine(self) -> None:
            # QWebEngineProfile must outlive every Page/View created from it.
            # _profile, _page, and _view are otherwise independent children of
            # this dialog, so leaving their destruction to Qt's default
            # parent/child teardown order crashes with "Release of profile
            # requested but WebEnginePage still not deleted." Detach and
            # schedule deletion in the safe order explicitly, from every path
            # that ends the dialog (success and cancel/close alike).
            if self._done:
                return
            self._done = True
            self._view.setPage(None)
            self._page.deleteLater()
            self._profile.deleteLater()

        def _emit_cookie(self, cookie_str: str) -> None:
            if self._done:
                return
            self._teardown_webengine()
            self._status_msg.setText("Sign-in complete")
            self.cookie_ready.emit(cookie_str)
            self.accept()

        def reject(self) -> None:
            self._teardown_webengine()
            super().reject()


class VpnPage(Page):
    """Connect to a VPN gateway using openconnect."""

    def __init__(self):
        super().__init__()
        self._worker: _VpnConnectWorker | None = None
        self._saml_pending = False
        self._gp_interface = "portal"
        self._pending_gateway_saml = False
        self._gateway_saml_attempted = False
        self._saml_gateway = ""
        self._saml_protocol = "gp"
        self._saml_os_emul = "win"
        self._saml_username = ""

        self._page_header(
            "Network & Internet",
            "VPN",
            "Connect to a VPN gateway using openconnect. Settings are saved for next time.",
        )

        # ── Connection settings card ──────────────────────────────────────────
        cfg_card, cfg_layout = _make_card()
        cfg_title = QLabel("Connection Settings")
        cfg_title.setObjectName("card-title")
        cfg_layout.addWidget(cfg_title)

        form_row = QHBoxLayout()
        form_row.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)

        def _lbl(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("card-copy")
            return lbl

        left.addWidget(_lbl("Gateway"))
        self._gw = QLineEdit()
        self._gw.setPlaceholderText("e.g. vpn.example.com")
        left.addWidget(self._gw)

        left.addWidget(_lbl("Protocol"))
        self._proto = QComboBox()
        self._proto.addItems(_VPN_PROTOCOLS)
        left.addWidget(self._proto)

        left.addWidget(_lbl("OS Emulation"))
        self._os_emul = QComboBox()
        self._os_emul.addItems(_VPN_OS_OPTIONS)
        left.addWidget(self._os_emul)

        right.addWidget(_lbl("Username"))
        self._vpn_user = QLineEdit()
        self._vpn_user.setPlaceholderText("optional")
        right.addWidget(self._vpn_user)

        right.addWidget(_lbl("Password"))
        self._vpn_pass = QLineEdit()
        self._vpn_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._vpn_pass.setPlaceholderText("optional — leave blank for interactive / SSO auth")
        right.addWidget(self._vpn_pass)

        right.addStretch()

        form_row.addLayout(left, 1)
        form_row.addLayout(right, 1)
        cfg_layout.addLayout(form_row)
        self._add(cfg_card)

        # ── Status + controls card ────────────────────────────────────────────
        ctrl_card, ctrl_layout = _make_card()

        self._vpn_status = QLabel("● Disconnected")
        self._vpn_status.setObjectName("status-dim")
        ctrl_layout.addWidget(self._vpn_status)

        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setMinimumHeight(34)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setMinimumHeight(34)
        self._disconnect_btn.setEnabled(False)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        btn_row.addStretch()
        ctrl_layout.addLayout(btn_row)

        self._vpn_log_toggle = QPushButton("Show details")
        self._vpn_log_toggle.setCheckable(True)
        self._vpn_log_toggle.setChecked(False)
        self._vpn_log_toggle.setObjectName("btn-secondary")
        ctrl_layout.addWidget(self._vpn_log_toggle)

        self._vpn_log = QTextEdit()
        self._vpn_log.document().setMaximumBlockCount(5000)
        self._vpn_log.setReadOnly(True)
        self._vpn_log.setStyleSheet(
            "font-family: 'Noto Mono', 'Cascadia Code', monospace; font-size: 12px;"
        )
        self._vpn_log.setVisible(False)
        self._vpn_log.setMinimumHeight(160)
        ctrl_layout.addWidget(self._vpn_log)

        self._vpn_log_toggle.toggled.connect(
            lambda checked: _set_log_panel(self._vpn_log_toggle, self._vpn_log, checked)
        )

        self._add(ctrl_card)
        self._stretch()

        self._load_vpn_saved()

    def _load_vpn_saved(self) -> None:
        v = _load_vpn_config()
        self._gw.setText(v.get("gateway", ""))
        idx = self._proto.findText(v.get("protocol", "gp"))
        if idx >= 0:
            self._proto.setCurrentIndex(idx)
        idx = self._os_emul.findText(v.get("os", "win"))
        if idx >= 0:
            self._os_emul.setCurrentIndex(idx)
        self._vpn_user.setText(v.get("username", ""))

    def _vpn_config_widgets(self):
        return (self._gw, self._proto, self._os_emul, self._vpn_user, self._vpn_pass)

    def _on_connect(self) -> None:
        gateway = self._gw.text().strip()
        if not gateway:
            _set_log_panel(self._vpn_log_toggle, self._vpn_log, True)
            self._vpn_log.append("[Error: Gateway is required]")
            return

        protocol = self._proto.currentText()
        os_emul = self._os_emul.currentText()
        username = self._vpn_user.text().strip()
        password = self._vpn_pass.text()

        _save_vpn_config(gateway, protocol, os_emul, username)

        self._saml_gateway = gateway
        self._saml_protocol = protocol
        self._saml_os_emul = os_emul
        self._saml_username = username
        self._saml_pending = False
        self._gp_interface = "portal"
        self._pending_gateway_saml = False
        self._gateway_saml_attempted = False

        self._vpn_log.clear()
        self._set_vpn_status("connecting")
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
        for w in self._vpn_config_widgets():
            w.setEnabled(False)

        cmd = [
            "sudo", "-E", "-A", "/usr/bin/openconnect",
            "--protocol", protocol,
            "--os", os_emul,
            "--script", "/usr/libexec/kyth-vpnc-script",
        ]
        if username:
            cmd += ["--user", username]
        if password:
            cmd += ["--passwd-on-stdin"]
        cmd.append(gateway)

        self._start_vpn_worker(cmd, password)

    def _on_disconnect(self) -> None:
        if self._worker:
            self._worker.stop()

    def _on_vpn_line(self, line: str) -> None:
        _set_log_panel(self._vpn_log_toggle, self._vpn_log, True)
        self._vpn_log.append(_redact_vpn_log_line(line))
        sb = self._vpn_log.verticalScrollBar()
        sb.setValue(sb.maximum())
        if _vpn_line_is_connected(line):
            self._set_vpn_status("connected")
            return
        m = _GP_PRELOGIN_IFACE_RE.search(line)
        if m:
            self._gp_interface = "portal" if m.group(1) == "global-protect" else "gateway"
            return
        if (
            "fgets (stdin)" in line
            and self._gp_interface == "gateway"
            and not self._saml_pending
            and not self._gateway_saml_attempted
        ):
            # Portal accepted the SAML cookie, but the gateway then demanded
            # its own prelogin-cookie (the portal cookie is interface-bound and
            # the portal returned no portal-userauthcookie to carry over).
            # openconnect prompted for it on an exhausted stdin and died — redo
            # SAML directly against the gateway once this process exits.
            self._pending_gateway_saml = True
            return
        if "Unexpected 512 result from server" in line:
            self._vpn_log.append(
                "[Hint: the GlobalProtect server rejected the SAML token — "
                "usually a portal/gateway mismatch or a username that doesn't "
                "match the SAML account]"
            )

    def _start_vpn_worker(self, cmd: list[str], stdin_text: str = "") -> None:
        worker = _VpnConnectWorker(cmd, stdin_text)
        self._worker = worker
        worker.line.connect(self._on_vpn_line)
        worker.done.connect(lambda code, w=worker: self._on_vpn_done(w, code))
        worker.saml_required.connect(self._on_saml_required)
        worker.start()

    def _on_vpn_done(self, worker: _VpnConnectWorker, code: int) -> None:
        if worker is not self._worker:
            worker.deleteLater()
            return
        self._worker = None
        worker.deleteLater()
        if self._saml_pending:
            return
        if self._pending_gateway_saml:
            self._pending_gateway_saml = False
            self._gateway_saml_attempted = True
            self._vpn_log.append(
                "[GP] Gateway requires its own SAML sign-in — restarting "
                "authentication against the gateway interface…"
            )
            QTimer.singleShot(500, self._start_gateway_probe)
            return
        self._set_vpn_status("disconnected")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        for w in self._vpn_config_widgets():
            w.setEnabled(True)
        self._vpn_log.append(f"\n[openconnect exited: code {code}]")

    def _start_gateway_probe(self) -> None:
        """Re-run the openconnect SAML probe against the GP gateway interface.

        Used when the portal leg succeeded but the gateway demanded its own
        prelogin-cookie, which only a gateway-issued SAML login can provide.
        The probe prints the gateway's SAML URL, the embedded browser replays
        the (now session-cached) IdP login, and the reconnect then uses
        gateway:<field>.
        """
        self._gp_interface = "gateway"
        self._set_vpn_status("connecting")
        cmd = [
            "sudo", "-E", "-A", "/usr/bin/openconnect",
            "--protocol", self._saml_protocol,
            "--os", self._saml_os_emul,
            "--script", "/usr/libexec/kyth-vpnc-script",
            "--usergroup", "gateway",
        ]
        if self._saml_username:
            cmd += ["--user", self._saml_username]
        cmd.append(self._saml_gateway)
        self._start_vpn_worker(cmd)

    def _on_saml_required(self, saml_url: str) -> None:
        if not _WEBENGINE_AVAILABLE:
            self._vpn_log.append(
                "\n[SAML auth required but python3-pyqt6-webengine is not installed]"
            )
            return
        self._saml_pending = True
        dlg = SamlBrowserDialog(saml_url, self)
        dlg.cookie_ready.connect(self._on_saml_cookie)
        dlg.rejected.connect(self._on_saml_cancelled)
        dlg.exec()
        dlg.deleteLater()

    def _on_saml_cookie(self, cookie: str) -> None:
        self._saml_pending = False
        self._vpn_log.append("[SAML authentication complete — reconnecting…]")
        if self._worker:
            self._worker.stop()
            if not self._worker.wait(10000):
                self._vpn_log.append("[Error: timed out waiting for the first openconnect process to exit]")
                return
        field, value, saml_username = _parse_gp_saml_cookie(cookie)
        cmd = [
            "sudo", "-E", "-A", "/usr/bin/openconnect",
            "--protocol", self._saml_protocol,
            "--os", self._saml_os_emul,
            "--script", "/usr/libexec/kyth-vpnc-script",
        ]
        worker_stdin = ""
        if self._saml_protocol == "gp" and field and value:
            cmd += ["--passwd-on-stdin", "--usergroup", f"{self._gp_interface}:{field}"]
            worker_stdin = value
            print(f"[SAML dbg] reconnecting via {self._gp_interface} with {field} and username={'yes' if (self._saml_username or saml_username) else 'no'}")
        else:
            cmd += ["--cookie", cookie]
        # The GP prelogin-cookie is bound to the SAML identity — the server
        # 512s if --user doesn't match it exactly, so it wins over the form.
        username = saml_username or self._saml_username
        if username:
            cmd += ["--user", username]
        cmd.append(self._saml_gateway)

        self._start_vpn_worker(cmd, worker_stdin)

    def _on_saml_cancelled(self) -> None:
        self._saml_pending = False
        self._set_vpn_status("disconnected")
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
        for w in self._vpn_config_widgets():
            w.setEnabled(True)
        self._vpn_log.append("\n[SAML authentication cancelled]")

    def _set_vpn_status(self, state: str) -> None:
        if state == "connected":
            self._vpn_status.setText("● Connected")
            self._vpn_status.setObjectName("status-ok")
        elif state == "connecting":
            self._vpn_status.setText("● Connecting…")
            self._vpn_status.setObjectName("status-warn")
        else:
            self._vpn_status.setText("● Disconnected")
            self._vpn_status.setObjectName("status-dim")
        _restyle(self._vpn_status)

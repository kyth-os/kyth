
# __KYTH_GENERATED_IMPORTS__


# KythOS theme: slate-blue surfaces, blue accent focus, restrained status colors.
# Palette:
#   window      #0c0e16      sidebar          #12141f
#   card        #151722      card hover       #1f2335
#   border      #26293a      strong border    #2e324c
#   input       #181b28      log/console      #1a1a1a
#   text        #ffffff      secondary text   #a6a6a6
#   accent      #4f8cff      accent (light)   #8fb8ff
#   ok #5fb88a   warn #d6a35c   error #ff99a4   danger button #c42b1c
QSS = """
* {
    font-family: "Noto Sans", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #e8e8e8;
}

QMainWindow,
QWidget#content-area {
    background: #0c0e16;
}

QWidget {
    background: transparent;
}

QLabel {
    background: transparent;
}

QScrollArea {
    background: transparent;
    border: none;
}

QToolTip {
    background: #151722;
    color: #e8e8e8;
    border: 1px solid #2e324c;
    padding: 4px 8px;
}

/* ── Top command bar ─────────────────────────────────────────────────────── */
QWidget#topbar {
    background: #12141f;
    border-bottom: 1px solid #1e2230;
}

QPushButton#topbar-nav {
    background: transparent;
    color: #e8e8e8;
    border: none;
    border-radius: 5px;
    padding: 4px 0;
    font-size: 15px;
    font-weight: 400;
}

QPushButton#topbar-nav:hover {
    background: #181b28;
}

QPushButton#topbar-nav:pressed {
    background: #1e2230;
}

QPushButton#topbar-nav:disabled {
    color: #5c5c5c;
    background: transparent;
}

QPushButton#breadcrumb-link {
    background: transparent;
    color: #e8e8e8;
    border: none;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 600;
    text-align: left;
}

QPushButton#breadcrumb-link:hover {
    background: #181b28;
    color: #ffffff;
}

QLabel#breadcrumb {
    color: #a6a6a6;
    font-size: 13px;
}

QLineEdit#search-box {
    background: #181b28;
    color: #e8e8e8;
    border: 1px solid #26293a;
    border-bottom: 1px solid #5c5c5c;
    border-radius: 5px;
    padding: 6px 12px;
}

QLineEdit#search-box:focus {
    background: #1f1f1f;
    border-bottom: 2px solid #8fb8ff;
}

QFrame#search-results-panel {
    background: #12141f;
    border-bottom: 1px solid #1e2230;
}

QLabel#search-results-title {
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
}

QLabel#search-results-hint {
    color: #8a8a8a;
    font-size: 11px;
}

QPushButton#search-result {
    background: #151722;
    color: #dcdcdc;
    border: 1px solid #26293a;
    border-radius: 6px;
    padding: 8px 12px;
    text-align: left;
    font-size: 12px;
    line-height: 1.35;
}

QPushButton#search-result:hover {
    background: #181b28;
    color: #ffffff;
    border-color: #2e324c;
}

QPushButton#search-result:pressed {
    background: #0c0e16;
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
QWidget#sidebar {
    background: #0c0e16;
    border-right: 1px solid #1e2230;
    border-left: 4px solid #4f8cff;
}

QWidget#sidebar-header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1c253d, stop:1 #12141f);
    border-bottom: 1px solid #1e2230;
}

QLabel#sidebar-logo {
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
    padding: 0;
}

QLabel#sidebar-ver {
    font-size: 11px;
    color: #a6a6a6;
    font-weight: 500;
    padding: 0;
}

QLabel#nav-section {
    font-size: 11px;
    font-weight: 600;
    color: #8a8a8a;
    padding: 0 0 2px 0;
}

QPushButton#nav-item,
QPushButton#nav-item-active {
    background: transparent;
    border: none;
    border-radius: 6px;
    margin: 1px 8px;
    padding: 8px 10px;
    text-align: left;
    font-size: 13px;
}

QPushButton#nav-item {
    color: #d6d6d6;
    font-weight: 400;
}

QPushButton#nav-item:hover {
    background: #181b28;
    color: #ffffff;
}

QPushButton#nav-item:pressed {
    background: #1e2230;
}

QPushButton#nav-item-active {
    background: #181b28;
    color: #ffffff;
    border-left: 3px solid #8fb8ff;
    padding: 8px 10px 8px 7px;
    font-weight: 600;
}

/* ── Page header band ────────────────────────────────────────────────────── */
QWidget#page-header {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1e2230, stop:1 #0c0e16);
    border-bottom: 1px solid #1e2230;
}

QLabel#eyebrow {
    color: #8fb8ff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 0;
}

QLabel#heading {
    font-size: 30px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#subheading {
    font-size: 13px;
    color: #a6a6a6;
    line-height: 1.5;
}

QLabel#section-heading {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
}

/* ── Status labels ───────────────────────────────────────────────────────── */
QLabel#status-ok {
    color: #5fb88a;
    font-weight: 600;
}

QLabel#status-warn {
    color: #d6a35c;
    font-weight: 600;
}

QLabel#status-err {
    color: #ff99a4;
    font-weight: 600;
}

QLabel#status-dim {
    color: #8a8a8a;
}

QLabel#task-status-idle,
QLabel#task-status-running,
QLabel#task-status-ok,
QLabel#task-status-warn,
QLabel#task-status-err {
    border-radius: 5px;
    padding: 8px 10px;
    font-weight: 600;
}

QLabel#task-status-idle {
    background: #151722;
    color: #a6a6a6;
    border: 1px solid #26293a;
}

QLabel#task-status-running {
    background: #1c253d;
    color: #c2d9ff;
    border: 1px solid #3d5d8a;
}

QLabel#task-status-ok {
    background: #1e2b24;
    color: #8fd1ab;
    border: 1px solid #3f7a5c;
}

QLabel#task-status-warn {
    background: #2e2417;
    color: #d6a35c;
    border: 1px solid #8a6534;
}

QLabel#task-status-err {
    background: #35262a;
    color: #ff99a4;
    border: 1px solid #5e3338;
}

QFrame#action-row {
    background: transparent;
    border: none;
}

QFrame#command-result-panel {
    background: transparent;
    border: none;
}

QFrame#empty-state {
    background: #151722;
    border: 1px dashed #2e324c;
    border-radius: 6px;
}

QLabel#empty-state-title {
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
}

QLabel#empty-state-copy {
    color: #a6a6a6;
    line-height: 1.5;
}

QFrame#flow-step {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 6px;
}

QLabel#flow-step-num {
    background: #1c253d;
    color: #c2d9ff;
    border: 1px solid #3d5d8a;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}

QLabel#flow-step-title {
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
}

QLabel#flow-step-copy {
    color: #a6a6a6;
    line-height: 1.45;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {
    background: #181b28;
    color: #e8e8e8;
    border: 1px solid #26293a;
    border-radius: 5px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 400;
}

QPushButton:hover {
    background: #1f2335;
    color: #ffffff;
    border-color: #454545;
}

QPushButton:pressed {
    background: #1e2230;
    color: #cfcfcf;
}

QPushButton:disabled {
    background: #12141f;
    color: #6b6b6b;
    border-color: #303030;
}

QPushButton#primary,
QPushButton#btn-secondary {
    background: #4f8cff;
    color: #ffffff;
    border: 1px solid #8fb8ff;
    font-weight: 600;
    padding: 8px 20px;
    letter-spacing: 0.3px;
}

QPushButton#primary:hover,
QPushButton#btn-secondary:hover {
    background: #8fb8ff;
    border-color: #8fb8ff;
}

QPushButton#primary:pressed,
QPushButton#btn-secondary:pressed {
    background: #3a6fd1;
}

QPushButton#primary:disabled,
QPushButton#btn-secondary:disabled {
    background: #181b28;
    color: #6b6b6b;
    border-color: #303030;
}

QPushButton#danger {
    background: #c42b1c;
    color: #ffffff;
    border: 1px solid #d13438;
    font-weight: 600;
}

QPushButton#danger:hover {
    background: #d13438;
    border-color: #ff6b6b;
}

QPushButton#danger:pressed {
    background: #a72015;
}

QPushButton#danger:disabled {
    background: #2d1d1c;
    color: #6b5252;
    border-color: #3a2a29;
}

QPushButton#branch-active {
    background: #4f8cff;
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #8fb8ff;
    border-radius: 5px;
    padding: 9px 22px;
}

QPushButton#branch-inactive {
    background: #181b28;
    color: #a6a6a6;
    border: 1px solid #26293a;
    border-radius: 5px;
    padding: 9px 22px;
}

QPushButton#branch-inactive:hover {
    background: #1f2335;
    color: #e8e8e8;
    border-color: #454545;
}

/* ── Control Panel home: category grid ───────────────────────────────────── */
QFrame#cp-category {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 10px;
}

QFrame#cp-category:hover {
    background: #1f2335;
    border-color: #2e324c;
}

QPushButton#cp-category-title {
    background: transparent;
    color: #ffffff;
    border: none;
    padding: 0;
    font-size: 15px;
    font-weight: 600;
    text-align: left;
}

QPushButton#cp-category-title:hover {
    color: #8fb8ff;
}

QPushButton#task-link {
    background: transparent;
    color: #8fb8ff;
    border: none;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
    font-weight: 400;
    text-align: left;
}

QPushButton#task-link:hover {
    background: #383838;
    color: #c2d9ff;
}

QPushButton#task-link:pressed {
    color: #4f8cff;
}

/* ── Gaming section switcher ─────────────────────────────────────────────── */
QFrame#gaming-section-switcher {
    background: transparent;
    border: none;
}

QWidget#gaming-section-row {
    background: transparent;
}

QPushButton#gaming-section,
QPushButton#gaming-section-active {
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton#gaming-section {
    background: #151722;
    color: #a6a6a6;
    border: 1px solid #26293a;
}

QPushButton#gaming-section:hover {
    background: #181b28;
    color: #ffffff;
    border-color: #2e324c;
}

QPushButton#gaming-section-active {
    background: #1c253d;
    color: #ffffff;
    border: 1px solid #8fb8ff;
}

/* ── Cards ───────────────────────────────────────────────────────────────── */
QFrame#card,
QFrame#home-recommend-card,
QFrame#home-action-card,
QFrame#stat-tile,
QFrame#starter-pack,
QFrame#ready-panel,
QFrame#store-app-card,
QFrame#store-category-card {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 10px;
}

QFrame#card:hover,
QFrame#home-recommend-card:hover,
QFrame#home-action-card:hover,
QFrame#stat-tile:hover,
QFrame#store-app-card:hover,
QFrame#store-category-card:hover {
    background: #1f2335;
    border-color: #2e324c;
}

QLabel#card-title {
    font-size: 14px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#card-subtitle {
    font-size: 13px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#card-summary {
    color: #e8e8e8;
    font-weight: 600;
}

QLabel#card-action {
    color: #8fb8ff;
}

QLabel#card-copy {
    color: #a6a6a6;
    line-height: 1.6;
}

QFrame#home-recommend-card {
    background: #1c253d;
    border: 1px solid #3d5d8a;
    border-left: 5px solid #4f8cff;
    border-radius: 10px;
}

QLabel#home-kicker {
    color: #8fb8ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.5px;
}

QFrame#home-section {
    background: transparent;
    border: none;
}

QLabel#home-section-title {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}

QLabel#home-section-copy {
    color: #8a8a8a;
    font-size: 12px;
    line-height: 1.4;
}

QFrame#card-accent-ok {
    background: #1e2b24;
    border: 1px solid #3f7a5c;
    border-radius: 10px;
}

QFrame#card-accent-warn {
    background: #2e2417;
    border: 1px solid #8a6534;
    border-radius: 10px;
}

QFrame#card-accent-err {
    background: #35262a;
    border: 1px solid #5e3338;
    border-radius: 10px;
}

QLabel#home-action-icon {
    font-size: 13px;
    font-weight: 600;
    color: #8fb8ff;
}

QLabel#home-action-title {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#home-action-copy {
    color: #a6a6a6;
    line-height: 1.45;
}

QLabel#home-next-title {
    font-size: 24px;
    font-weight: 750;
    color: #ffffff;
}

QLabel#home-next-copy {
    color: #c5c5c5;
    line-height: 1.5;
}

QLabel#home-next-meta {
    color: #c2d9ff;
    line-height: 1.45;
}

QPushButton#starter-pack-header {
    background: transparent;
    border: none;
    color: #ffffff;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    padding: 0;
}

QPushButton#starter-pack-header:hover {
    color: #8fb8ff;
}

QLabel#starter-pack-meta {
    color: #8fb8ff;
    font-size: 11px;
    font-weight: 600;
}

QWidget#starter-pack-details {
    background: transparent;
}

QFrame#store-hero {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 6px;
}

QLabel#store-hero-title {
    font-size: 20px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#store-kicker {
    color: #8fb8ff;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}

QFrame#drop-card {
    background: #12141f;
    border: 1px dashed #2e324c;
    border-radius: 10px;
}

QFrame#drop-card-active {
    background: #1c253d;
    border: 2px dashed #8fb8ff;
    border-radius: 10px;
}

QLabel#drop-glyph {
    background: #181b28;
    color: #8fb8ff;
    border: 1px solid #26293a;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#drop-title {
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
}

/* ── Software page tab bar ───────────────────────────────────────────────── */
QWidget#sw-tab-bar {
    background: #12141f;
}

QPushButton#sw-tab,
QPushButton#sw-tab-active {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 10px 22px;
    font-size: 13px;
    min-width: 92px;
}

QPushButton#sw-tab {
    color: #a6a6a6;
    border-bottom: 2px solid transparent;
    font-weight: 400;
}

QPushButton#sw-tab:hover {
    background: #151722;
    color: #e8e8e8;
}

QPushButton#sw-tab-active {
    color: #ffffff;
    border-bottom: 2px solid #8fb8ff;
    font-weight: 600;
}

/* ── Stat tiles ──────────────────────────────────────────────────────────── */
QLabel#stat-label {
    font-size: 11px;
    font-weight: 600;
    color: #8a8a8a;
}

QLabel#stat-value {
    font-size: 16px;
    font-weight: 600;
    color: #e8e8e8;
}

QLabel#stat-value-ok {
    font-size: 16px;
    font-weight: 600;
    color: #5fb88a;
}

QLabel#stat-value-warn {
    font-size: 16px;
    font-weight: 600;
    color: #d6a35c;
}

/* ── Gaming readiness panel ──────────────────────────────────────────────── */
QLabel#ready-score {
    color: #5fb88a;
    font-size: 28px;
    font-weight: 700;
}

QLabel#ready-score-warn {
    color: #d6a35c;
    font-size: 28px;
    font-weight: 700;
}

QLabel#ready-score-err {
    color: #ff99a4;
    font-size: 28px;
    font-weight: 700;
}

QLabel#ready-row-ok,
QLabel#ready-row-warn,
QLabel#ready-row-err,
QLabel#ready-row-dim {
    border-radius: 5px;
    padding: 8px 10px;
    font-weight: 600;
}

QLabel#ready-row-ok {
    background: #1e2b24;
    color: #8fd1ab;
    border: 1px solid #3f7a5c;
}

QLabel#ready-row-warn {
    background: #2e2417;
    color: #d6a35c;
    border: 1px solid #8a6534;
}

QLabel#ready-row-err {
    background: #35262a;
    color: #ff99a4;
    border: 1px solid #5e3338;
}

QLabel#ready-row-dim {
    background: #151722;
    color: #a6a6a6;
    border: 1px solid #26293a;
}

/* ── Hardware cards ──────────────────────────────────────────────────────── */
QFrame#hw-card-ok {
    background: #1e2b24;
    border: 1px solid #3f7a5c;
    border-left: 4px solid #5fb88a;
    border-radius: 8px;
}

QFrame#hw-card-ok:hover {
    background: #303a30;
    border: 1px solid #3f7a5c;
    border-left: 4px solid #5fb88a;
    border-radius: 8px;
}

QFrame#hw-card-warn {
    background: #2e2417;
    border: 1px solid #8a6534;
    border-left: 4px solid #d6a35c;
    border-radius: 8px;
}

QFrame#hw-card-warn:hover {
    background: #3a3525;
    border: 1px solid #8a6534;
    border-left: 4px solid #d6a35c;
    border-radius: 8px;
}

QFrame#hw-card-err {
    background: #35262a;
    border: 1px solid #5e3338;
    border-left: 4px solid #ff99a4;
    border-radius: 8px;
}

QFrame#hw-card-err:hover {
    background: #3b2d2f;
    border: 1px solid #6e3d42;
    border-left: 4px solid #ff99a4;
    border-radius: 8px;
}

QFrame#hw-card-dim {
    background: #151722;
    border: 1px solid #26293a;
    border-left: 4px solid #5c5c5c;
    border-radius: 8px;
}

QFrame#hw-card-dim:hover {
    background: #333333;
    border: 1px solid #484848;
    border-left: 4px solid #6b6b6b;
    border-radius: 8px;
}

/* ── Divider ─────────────────────────────────────────────────────────────── */
QFrame#divider {
    background: #1e2230;
    max-height: 1px;
    border: none;
}

/* ── Text log ────────────────────────────────────────────────────────────── */
QTextEdit {
    background: #1a1a1a;
    color: #d4d4d4;
    border: 1px solid #26293a;
    border-radius: 5px;
    font-family: "Cascadia Code", "Noto Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 12px 14px;
    selection-background-color: #1c253d;
}

/* ── Progress bar ────────────────────────────────────────────────────────── */
QProgressBar {
    background: #181b28;
    border: none;
    border-radius: 3px;
    max-height: 5px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background: #4f8cff;
    border-radius: 3px;
}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}

QScrollBar::handle:vertical {
    background: #2e324c;
    border-radius: 4px;
    min-height: 28px;
}

QScrollBar::handle:vertical:hover {
    background: #5c5c5c;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #2e324c;
    border-radius: 4px;
    min-width: 28px;
}

QScrollBar::handle:horizontal:hover {
    background: #5c5c5c;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: transparent;
}

/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit {
    background: #181b28;
    border: 1px solid #26293a;
    border-bottom: 1px solid #5c5c5c;
    border-radius: 5px;
    padding: 7px 11px;
    color: #e8e8e8;
    selection-background-color: #1c253d;
}

QLineEdit:focus {
    background: #1f1f1f;
    border-bottom: 2px solid #8fb8ff;
}

QCheckBox {
    color: #e8e8e8;
    spacing: 9px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background: #181b28;
    border: 1px solid #5c5c5c;
    border-radius: 4px;
}

QCheckBox::indicator:checked {
    background: #4f8cff;
    border-color: #4f8cff;
}

QCheckBox::indicator:hover {
    border-color: #8fb8ff;
}

QComboBox {
    background: #181b28;
    border: 1px solid #26293a;
    border-radius: 5px;
    padding: 7px 11px;
    color: #e8e8e8;
    min-width: 80px;
}

QComboBox:hover {
    border-color: #2e324c;
    background: #1f2335;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    background: #151722;
    border: 1px solid #26293a;
    color: #e8e8e8;
    selection-background-color: #181b28;
    outline: none;
}

/* ── Live session banner ─────────────────────────────────────────────────── */
QWidget#live-banner {
    background: #2e2417;
    border-bottom: 1px solid #8a6534;
}

QLabel#live-banner-badge {
    background: #151722;
    color: #d6a35c;
    border: 1px solid #8a6534;
    border-radius: 10px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QLabel#live-banner-text {
    color: #e8c08a;
    font-size: 11px;
}

/* ── Wizard ──────────────────────────────────────────────────────────────── */
QWidget#wizard-header {
    background: #12141f;
    border-bottom: 1px solid #1e2230;
}

QWidget#wizard-footer {
    background: #12141f;
    border-top: 1px solid #1e2230;
}

QLabel#wizard-footer-hint {
    color: #a6a6a6;
    font-size: 12px;
}

QLabel#step-dot-active {
    background: #8fb8ff;
    border-radius: 5px;
}

QLabel#step-dot-done {
    background: #4f8cff;
    border-radius: 5px;
}

QLabel#step-dot-inactive {
    background: #2e324c;
    border-radius: 5px;
}

QLabel#wizard-progress-step {
    font-size: 11px;
    font-weight: 400;
    color: #8a8a8a;
}

QLabel#wizard-progress-step-active {
    font-size: 11px;
    font-weight: 600;
    color: #ffffff;
}

QLabel#wizard-progress-step-done {
    font-size: 11px;
    font-weight: 400;
    color: #8fb8ff;
}

QWidget#wizard-hero {
    background: #12141f;
}

QLabel#wizard-logo {
    font-size: 48px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -1px;
}

QLabel#wizard-tagline {
    font-size: 16px;
    color: #8fb8ff;
    font-weight: 600;
}

QLabel#wizard-desc {
    font-size: 13px;
    color: #a6a6a6;
    line-height: 1.6;
}

QLabel#finish-title {
    font-size: 26px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#finish-subtitle {
    font-size: 14px;
    color: #a6a6a6;
    line-height: 1.6;
}
"""

QSS += """
/* Modern System Hub overlay.
   Keep this after the base theme so every hub page uses the same surface,
   spacing, control, and status language without touching page behavior. */
QWidget {
    background-color: #0c0e16;
    color: #f4f6f8;
    font-size: 13px;
}

QScrollArea,
QScrollArea > QWidget > QWidget {
    background: transparent;
    border: 0;
}

QFrame#card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#card-accent-err,
QFrame#card-accent-dim,
QFrame#hw-card-dim {
    background-color: #151722;
    border: 1px solid #26293a;
    border-radius: 8px;
}

QFrame#card-accent-ok {
    border-left: 4px solid #5fb88a;
}

QFrame#card-accent-warn {
    border-left: 4px solid #d6a35c;
}

QFrame#card-accent-err {
    border-left: 4px solid #e05f67;
}

QFrame#card-accent-dim,
QFrame#hw-card-dim {
    border-left: 4px solid #66717f;
}

QLabel#card-title {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}

QLabel#card-summary,
QLabel#subheading,
QLabel#page-subtitle,
QLabel#wizard-desc {
    color: #aab4bf;
}

QLabel#page-eyebrow,
QLabel#eyebrow {
    color: #8fb8ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
}

QLabel#page-title,
QLabel#heading {
    color: #ffffff;
    font-size: 24px;
    font-weight: 750;
}

QPushButton {
    background-color: #23282f;
    border: 1px solid #3b444f;
    border-radius: 6px;
    color: #f7f9fb;
    font-weight: 650;
    padding: 8px 13px;
}

QPushButton:hover {
    background-color: #2b323b;
    border-color: #53606d;
}

QPushButton:pressed {
    background-color: #1d2228;
}

QPushButton:disabled {
    background-color: #191c20;
    border-color: #2a2f36;
    color: #707985;
}

QPushButton#primary,
QPushButton[primary="true"] {
    background-color: #4f8cff;
    border-color: #3d5d8a;
    color: #ffffff;
}

QPushButton#primary:hover,
QPushButton[primary="true"]:hover {
    background-color: #8fb8ff;
}

QLineEdit,
QTextEdit,
QComboBox,
QSpinBox {
    background-color: #12141f;
    border: 1px solid #333a43;
    border-radius: 6px;
    color: #f4f6f8;
    padding: 7px 9px;
    selection-background-color: #4f8cff;
}

QLineEdit:focus,
QTextEdit:focus,
QComboBox:focus,
QSpinBox:focus {
    border-color: #8fb8ff;
}

QProgressBar {
    background-color: #12141f;
    border: 1px solid #333a43;
    border-radius: 6px;
    color: #f4f6f8;
    text-align: center;
    min-height: 14px;
}

QProgressBar::chunk {
    background-color: #4f8cff;
    border-radius: 5px;
}

QListWidget,
QListView {
    background-color: #12141f;
    border: 1px solid #26293a;
    border-radius: 8px;
    outline: 0;
}

QListWidget::item,
QListView::item {
    border-radius: 6px;
    margin: 3px 6px;
    padding: 8px 10px;
}

QListWidget::item:selected,
QListView::item:selected {
    background-color: #1c253d;
    color: #ffffff;
}

QLabel#status-ok,
QLabel#task-status-ok {
    background-color: #1e2b24;
    border: 1px solid #3f7a5c;
    border-radius: 6px;
    color: #8fd1ab;
    padding: 4px 8px;
}

QLabel#status-warn,
QLabel#task-status-warn {
    background-color: #2e2417;
    border: 1px solid #8a6534;
    border-radius: 6px;
    color: #e8c08a;
    padding: 4px 8px;
}

QLabel#status-err,
QLabel#task-status-err {
    background-color: #3b1d22;
    border: 1px solid #9f464f;
    border-radius: 6px;
    color: #ffb0b6;
    padding: 4px 8px;
}

QLabel#status-dim,
QLabel#task-status-dim {
    background-color: #20252b;
    border: 1px solid #3d4651;
    border-radius: 6px;
    color: #aab4bf;
    padding: 4px 8px;
}
"""

QSS += """
/* Home polish pass: keep text transparent and move structure to panels. */
QWidget#page,
QScrollArea,
QScrollArea > QWidget,
QWidget#scroll-content {
    background: #0c0e16;
}

QLabel {
    background: transparent;
}

QFrame#card,
QFrame#card-accent-ok,
QFrame#card-accent-warn,
QFrame#stat-tile,
QFrame#summary-tile,
QFrame#home-action,
QFrame#home-section-header {
    background: #151722;
    border: 1px solid #26293a;
    border-radius: 8px;
}

QFrame#card,
QFrame#home-section-header {
    padding: 0;
}

QFrame#card-accent-ok {
    background: #1e2b24;
    border-color: #3f7a5c;
}

QFrame#card-accent-warn {
    background: #2e2417;
    border-color: #8a6534;
}

QFrame#stat-tile {
    background: #151722;
    border-color: #44494c;
}

QFrame#stat-tile:hover,
QFrame#summary-tile:hover,
QFrame#home-action:hover {
    background: #1f2335;
    border-color: #5a666b;
}

QLabel#home-section-title {
    color: #f4f7f8;
    font-size: 20px;
    font-weight: 700;
}

QLabel#home-section-subtitle,
QLabel#card-copy,
QLabel#stat-label {
    color: #b8c6cc;
}

QLabel#home-kicker {
    color: #8fb8ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#stat-value {
    color: #f0f4f5;
    font-size: 16px;
    font-weight: 600;
}

QLabel#stat-value-ok {
    color: #8fd1ab;
}

QLabel#stat-value-warn {
    color: #e8c08a;
}

QPushButton#primary:hover {
    background: #8fb8ff;
}

/* ── Gen Z Redesign Styles ──────────────────────────────────────────────── */
QFrame#genz-hero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1e29, stop:0.5 #281d3d, stop:1 #1c2b36);
    border: 1px solid #483d73;
    border-radius: 16px;
}

QLabel#genz-hero-title {
    font-size: 28px;
    font-weight: 850;
    color: #ffffff;
}

QLabel#genz-hero-subtitle {
    font-size: 13px;
    color: #aab4bf;
}

QLabel#glowing-pill-ok {
    background-color: #122e22;
    border: 1px solid #10b981;
    color: #34d399;
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 800;
}

QLabel#glowing-pill-warn {
    background-color: #2a1f10;
    border: 1px solid #f59e0b;
    color: #fbbf24;
    border-radius: 12px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 800;
}

QWidget#genz-focus-row {
    background-color: #12141f;
    border: 1px solid #26293a;
    border-radius: 12px;
}

QPushButton#genz-mode-btn {
    background-color: #12141f;
    border: 1px solid #26293a;
    border-radius: 8px;
    color: #aab4bf;
    font-weight: 750;
    padding: 8px 18px;
}

QPushButton#genz-mode-btn:hover {
    border-color: #4f8cff;
    color: #ffffff;
}

QPushButton#genz-mode-btn:checked {
    background-color: #4f8cff;
    border-color: #8fb8ff;
    color: #ffffff;
}

QFrame#genz-hud-card {
    background-color: #151722;
    border: 1px solid #26293a;
    border-radius: 14px;
}

QFrame#genz-hud-card:hover {
    border-color: #4f8cff;
    background-color: #242933;
}

QLabel#hud-title {
    color: #ffffff;
    font-size: 14px;
    font-weight: 750;
}

QLabel#hud-desc {
    color: #aab4bf;
    font-size: 12px;
}

QFrame#genz-category-card {
    background-color: #151722;
    border: 1px solid #26293a;
    border-radius: 14px;
}

QFrame#genz-category-card:hover {
    background-color: #242933;
}

QFrame#genz-category-gaming {
    border-left: 5px solid #a855f7;
}

QFrame#genz-category-apps {
    border-left: 5px solid #06b6d4;
}

QFrame#genz-category-system {
    border-left: 5px solid #10b981;
}

QFrame#genz-category-network {
    border-left: 5px solid #f59e0b;
}

QFrame#genz-category-advanced {
    border-left: 5px solid #ec4899;
}

QPushButton#genz-category-title {
    background: transparent;
    color: #ffffff;
    border: none;
    padding: 0;
    font-size: 16px;
    font-weight: 750;
    text-align: left;
}

QPushButton#genz-category-title:hover {
    color: #8fb8ff;
}

QPushButton#genz-task-link {
    background: transparent;
    color: #8fb8ff;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: 600;
    text-align: left;
}

QPushButton#genz-task-link:hover {
    background-color: #2b323c;
    color: #c2d9ff;
}
"""

/* global document, loadDisks, initKernel, initConfig, buildReview, loadRescue */
/* exported goto */
// Wizard step navigation — the one thing every step page needs, split out
// on its own (was previously the top of app.js, a single 1352-line file
// covering every step) so it can load first and the step files that follow
// (disk.js, kernel.js, config.js, review.js, partition-editor.js,
// install-flow.js) stay independently readable.
const STEPS = ['welcome','disk','kernel','config','review','install'];

// eslint-disable-next-line no-unused-vars -- called from index.html onclick= and other step files
function goto(name) {
  document.querySelectorAll('.page').forEach(p => { p.classList.remove('active'); });
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.step').forEach(el => {
    const si = STEPS.indexOf(el.dataset.step), ai = STEPS.indexOf(name);
    el.classList.toggle('done',   si < ai);
    el.classList.toggle('active', si === ai);
    // ai may be -1 for non-step pages (error, done) — never pass '' to remove()
    if (si < ai)  el.classList.remove('active');
    if (si === ai) el.classList.remove('done');
  });
  if (name === 'disk')    loadDisks();
  if (name === 'kernel')  initKernel();
  if (name === 'config')  initConfig();
  if (name === 'review')  buildReview();
  if (name === 'rescue')  loadRescue();
}

(function () {
  var T = {
    en: {
      tagline: '.sim prototype', example: 'Example', recipe: 'Recipe', translateTo: 'Translate to {x}', copy: 'Copy', copied: 'Copied',
      noIssues: 'No problems found. The recipe runs as written.', blocked: 'Fix the errors to run this version. The last valid recipe keeps running.',
      error: 'error', warn: 'warning', pause: 'Pause', play: 'Play', replay: 'Run again', restart: 'Restart', speed: 'Speed',
      controls: 'Controls', scenarios: 'Scenarios', recipeValues: 'Recipe values', metrics: 'Metrics', live: 'this run so far',
      range: '{n} runs: {a} to {b}, median {m}', rangeCalc: 'Running {d} of {t} simulations', compare: 'Scenario comparison',
      compareNote: 'Median of {n} runs per column, with the p10 to p90 range underneath.', current: 'Current settings', apply: 'Apply',
      finished: 'Finished', dayOf: 'Day {d} of {t}', peak: 'peak ×{f}', closed: 'arrivals closed', busy: '{b} of {q} busy', offShift: 'off shift', waiting: '{n} waiting',
      noQueue: 'no queue', arrivals: 'Arrivals', after: 'after {x}', otherwise: 'otherwise', footer: 'A model, not a forecast. The example numbers are illustrative.',
      count: 'Count', shareKind: 'Share of finished items', wait: 'Wait p{p} at {x}', queue: 'Average queue at {x}', util: 'Utilization of {x}',
      cost: 'Cost per {x}', per: { day: 'day', week: 'week', month: 'month', year: 'year' }, simulates: 'Simulates {h}', seed: 'seed {s}',
      noControls: 'This recipe has no controls. Add one with knob name min..max = value.', screen: 'Screen language',
      months: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
      units: { s: 's', min: 'min', h: 'h', d: 'days', d1: 'day', w: 'week', w1: 'week', mo: 'months', mo1: 'month', y: 'years', y1: 'year' }
    },
    pt: {
      tagline: 'protótipo .sim', example: 'Exemplo', recipe: 'Receita', translateTo: 'Traduzir para {x}', copy: 'Copiar', copied: 'Copiado',
      noIssues: 'Nenhum problema. A receita roda como está escrita.', blocked: 'Corrija os erros para rodar esta versão. A última receita válida continua rodando.',
      error: 'erro', warn: 'aviso', pause: 'Pausar', play: 'Rodar', replay: 'Rodar de novo', restart: 'Reiniciar', speed: 'Velocidade',
      controls: 'Controles', scenarios: 'Cenários', recipeValues: 'Valores da receita', metrics: 'Métricas', live: 'nesta rodada até agora',
      range: '{n} rodadas: de {a} a {b}, mediana {m}', rangeCalc: 'Rodando {d} de {t} simulações', compare: 'Comparação de cenários',
      compareNote: 'Mediana de {n} rodadas por coluna, com a faixa p10 a p90 embaixo.', current: 'Ajustes atuais', apply: 'Aplicar',
      finished: 'Concluído', dayOf: 'Dia {d} de {t}', peak: 'pico ×{f}', closed: 'chegadas fechadas', busy: '{b} de {q} ocupados', offShift: 'fora do turno', waiting: '{n} na fila',
      noQueue: 'sem fila', arrivals: 'Chegadas', after: 'após {x}', otherwise: 'senão', footer: 'Um modelo, não uma previsão. Os números dos exemplos são ilustrativos.',
      count: 'Contagem', shareKind: 'Fração dos itens concluídos', wait: 'Espera p{p} em {x}', queue: 'Fila média em {x}', util: 'Utilização de {x}',
      cost: 'Custo por {x}', per: { day: 'dia', week: 'semana', month: 'mês', year: 'ano' }, simulates: 'Simula {h}', seed: 'semente {s}',
      noControls: 'Esta receita não tem controles. Adicione um com controle nome min..max = valor.', screen: 'Idioma da tela',
      months: ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
      units: { s: 's', min: 'min', h: 'h', d: 'dias', d1: 'dia', w: 'semanas', w1: 'semana', mo: 'meses', mo1: 'mês', y: 'anos', y1: 'ano' }
    }
  };

  var $ = function (id) { return document.getElementById(id); };
  var S = {
    ui: typeof START_UI === 'string' ? START_UI : 'en', src: '', parsed: null, model: null, knobs: {}, plan: null, sim: null, simT: 0, playing: true, speed: 1,
    particles: [], acc: {}, layout: null, range: null, compare: null, colors: {}, lastCards: 0, job: 0
  };
  try { var saved = localStorage.getItem('bo-ui'); if (saved === 'pt' || saved === 'en') S.ui = saved; } catch (e) {}

  function tr(key, p) {
    var s = T[S.ui][key];
    if (typeof s !== 'string') return s;
    return s.replace(/\{(\w)\}/g, function (_, k) { return p && p[k] != null ? p[k] : ''; });
  }
  function loc() { return S.ui === 'pt' ? 'pt-BR' : 'en-US'; }
  function labelLocale() { return S.ui === 'pt' ? 'pt-BR' : 'en'; }
  function dn(id) {
    var L = S.model ? S.model.labels : {};
    return (L[labelLocale()] && L[labelLocale()][id]) || (L.en && L.en[id]) || String(id).replace(/_/g, ' ');
  }

  // ---------- formatting ----------
  function fmtNum(n, dec) {
    if (!isFinite(n)) return '–';
    var a = Math.abs(n);
    if (a >= 10000) return new Intl.NumberFormat(loc(), { notation: 'compact', maximumFractionDigits: 1 }).format(n);
    return new Intl.NumberFormat(loc(), { maximumFractionDigits: dec == null ? (a < 10 ? 1 : 0) : dec }).format(n);
  }
  function fmtPct(x) { return new Intl.NumberFormat(loc(), { style: 'percent', maximumFractionDigits: x < 0.1 ? 1 : 0 }).format(x); }
  function fmtMoney(x) {
    var cur = (S.plan && S.plan.currency) || 'USD';
    try {
      return new Intl.NumberFormat(loc(), { style: 'currency', currency: cur, notation: Math.abs(x) >= 100000 ? 'compact' : 'standard', maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 2 }).format(x);
    } catch (e) { return cur + ' ' + fmtNum(x); }
  }
  function fmtDur(min) {
    var u = T[S.ui].units;
    if (!isFinite(min)) return '–';
    if (min < 1) return fmtNum(min * 60, 0) + ' ' + u.s;
    if (min < 90) return fmtNum(min, min < 10 ? 1 : 0) + ' ' + u.min;
    if (min < 48 * 60) return fmtNum(min / 60, 1) + ' ' + u.h;
    return fmtNum(min / 1440, 1) + ' ' + u.d;
  }
  function fmtHorizon(min) {
    var u = T[S.ui].units, n;
    if (min >= 525600) { n = min / 525600; return fmtNum(n, 1) + ' ' + (n === 1 ? u.y1 : u.y); }
    if (min >= 43200) { n = min / 43200; return fmtNum(n, 1) + ' ' + (n === 1 ? u.mo1 : u.mo); }
    if (min >= 10080 && min % 10080 === 0) { n = min / 10080; return fmtNum(n, 0) + ' ' + (n === 1 ? u.w1 : u.w); }
    if (min >= 1440) { n = min / 1440; return fmtNum(n, 1) + ' ' + (n === 1 ? u.d1 : u.d); }
    return fmtDur(min);
  }
  function metricTitle(m) {
    if (m.kind === 'count') return dn(m.x);
    if (m.kind === 'share') return dn(m.x);
    if (m.kind === 'wait') return tr('wait', { p: m.pn, x: dn(m.x) });
    if (m.kind === 'queue') return tr('queue', { x: dn(m.x) });
    if (m.kind === 'util') return tr('util', { x: dn(m.x) });
    return tr('cost', { x: T[S.ui].per[m.perName] });
  }
  function metricKind(m) {
    if (m.kind === 'count') return tr('count');
    if (m.kind === 'share') return tr('shareKind');
    return '';
  }
  function fmtMetric(m, v) {
    if (m.kind === 'count') return fmtNum(Math.round(v), 0);
    if (m.kind === 'share' || m.kind === 'util') return fmtPct(v);
    if (m.kind === 'wait') return fmtDur(v);
    if (m.kind === 'queue') return fmtNum(v, v < 10 ? 1 : 0);
    return fmtMoney(v);
  }

  // ---------- theme colors for the canvas ----------
  function readColors() {
    var cs = getComputedStyle(document.documentElement), g = function (n) { return cs.getPropertyValue(n).trim(); };
    S.colors = { ink: g('--ink'), muted: g('--muted'), line: g('--line'), surface: g('--surface'), stage: g('--stage'),
      accent: g('--accent'), crit: g('--crit'), edge: g('--edge'), cats: [g('--cat1'), g('--cat2'), g('--cat3'), g('--cat4'), g('--cat5'), g('--cat6')] };
  }
  readColors();
  try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', readColors); } catch (e) {}
  new MutationObserver(readColors).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  // ---------- recipe handling ----------
  var editTimer = null;
  function setSource(src, keepKnobs) {
    S.src = src;
    $('src').value = src;
    renderGutter();
    handleSource(keepKnobs);
  }
  function handleSource(keepKnobs) {
    var r = SIMLANG.parse(S.src);
    var lang = r.model.lang;
    $('recipe-lang').textContent = 'lang ' + lang;
    $('translate').textContent = tr('translateTo', { x: lang === 'en' ? 'pt-BR' : 'en' });
    if (r.ok) {
      var M = r.model, knobs = {};
      M.knobOrder.forEach(function (k) {
        var K = M.knobs[k], prev = keepKnobs && S.knobs[k];
        knobs[k] = (prev != null && prev >= K.min && prev <= K.max && S.model && S.model.knobs[k] && S.model.knobs[k].pct === K.pct) ? prev : K.init;
      });
      S.model = M; S.knobs = knobs;
      rebuild();
      var fl = SIMLANG.flows(M, S.plan);
      fl.endless.forEach(function (x) { r.diags.push({ sev: 'warn', text: SIMLANG.fmtMsg('endless', { x: x }, lang) }); });
      fl.loads.forEach(function (ld) {
        if (ld.load > 1.001) {
          var stepName = S.plan.steps[ld.steps[0]].name;
          r.diags.push({ sev: 'warn', text: SIMLANG.fmtMsg('unstable', { x: stepName, v: Math.round(ld.load * 100) + '%' }, lang) });
        }
      });
      renderControls();
    }
    S.parsed = r;
    renderValidator();
  }
  function rebuild() {
    S.plan = SIMLANG.compile(S.model, S.knobs);
    S.flows = SIMLANG.flows(S.model, S.plan);
    restartLive();
    computeLayout();
    renderHeader();
    renderCards(true);
    renderLegend();
    scheduleJob();
  }
  function restartLive() {
    S.sim = new BO.Sim(S.plan, S.model.seed, { track: true });
    S.simT = 0; S.particles = []; S.acc = {};
    S.playing = true;
    updatePlay();
  }

  // ---------- validator ----------
  function renderValidator() {
    var box = $('validator'), r = S.parsed, html = '';
    if (!r.diags.length) html = '<p class="ok">' + esc(tr('noIssues')) + '</p>';
    else {
      html = '<ul>' + r.diags.map(function (d, i) {
        return '<li class="' + d.sev + '"><button type="button" data-line="' + (d.line || '') + '"><span class="sev">' + esc(tr(d.sev === 'error' ? 'error' : 'warn')) + '</span><span>' + esc(d.text) + '</span></button></li>';
      }).join('') + '</ul>';
      if (!r.ok) html += '<p class="blocked">' + esc(tr('blocked')) + '</p>';
    }
    box.innerHTML = html;
  }
  $('validator').addEventListener('click', function (e) {
    var b = e.target.closest('button[data-line]');
    if (!b || !b.dataset.line) return;
    var ln = +b.dataset.line, lines = S.src.split('\n'), start = 0;
    for (var i = 0; i < ln - 1; i++) start += lines[i].length + 1;
    var ta = $('src');
    ta.focus();
    ta.setSelectionRange(start, start + (lines[ln - 1] || '').length);
    ta.scrollTop = Math.max(0, (ln - 4) * parseFloat(getComputedStyle(ta).lineHeight));
  });
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  // ---------- editor ----------
  function renderGutter() {
    var n = S.src.split('\n').length, out = '';
    for (var i = 1; i <= n; i++) out += i + '\n';
    $('gutter').textContent = out;
    $('gutter').scrollTop = $('src').scrollTop;
  }
  $('src').addEventListener('input', function () {
    S.src = this.value;
    renderGutter();
    clearTimeout(editTimer);
    editTimer = setTimeout(function () { handleSource(true); }, 450);
  });
  $('src').addEventListener('scroll', function () { $('gutter').scrollTop = this.scrollTop; });
  $('src').addEventListener('keydown', function (e) {
    if (e.key === 'Tab' && !e.shiftKey) {
      e.preventDefault();
      var s = this.selectionStart, en = this.selectionEnd;
      this.value = this.value.slice(0, s) + '  ' + this.value.slice(en);
      this.selectionStart = this.selectionEnd = s + 2;
      this.dispatchEvent(new Event('input'));
    }
  });
  $('translate').addEventListener('click', function () {
    var to = SIMLANG.detectLang(S.src) === 'en' ? 'pt-BR' : 'en';
    setSource(SIMLANG.translate(S.src, to), true);
  });
  $('copy').addEventListener('click', function () {
    var btn = this, done = function () { btn.textContent = tr('copied'); setTimeout(function () { btn.textContent = tr('copy'); }, 1400); };
    try {
      navigator.clipboard.writeText(S.src).then(done, function () { $('src').select(); });
    } catch (e) { $('src').select(); }
  });
  EXAMPLES.forEach(function (ex) {
    var o = document.createElement('option');
    o.value = ex.id; o.textContent = ex.title;
    $('example').appendChild(o);
  });
  $('example').addEventListener('change', function () {
    var ex = EXAMPLES.filter(function (x) { return x.id === $('example').value; })[0];
    S.model = null;
    setSource(ex.src, false);
  });

  // ---------- header, clock and play ----------
  function renderHeader() {
    $('sim-name').textContent = S.model.name;
    $('sim-sub').textContent = tr('simulates', { h: fmtHorizon(S.plan.horizon) }) + ' · ' + tr('seed', { s: S.model.seed });
  }
  function updatePlay() {
    var b = $('play');
    b.textContent = S.sim && S.sim.finished ? tr('replay') : S.playing ? tr('pause') : tr('play');
    b.setAttribute('aria-pressed', S.playing ? 'true' : 'false');
  }
  $('play').addEventListener('click', function () {
    if (S.sim.finished) { restartLive(); return; }
    S.playing = !S.playing;
    updatePlay();
  });
  $('restart').addEventListener('click', restartLive);
  $('speed').addEventListener('change', function () { S.speed = +this.value; });

  function clockText() {
    var t = S.simT, H = S.plan.horizon, day = Math.floor(t / 1440), dom, m;
    var mins = Math.floor(t % 1440), hh = String(Math.floor(mins / 60)).padStart(2, '0'), mm = String(mins % 60).padStart(2, '0');
    if (H <= 1440) return hh + ':' + mm;
    m = BO.monthOf(day);
    var MS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
    dom = (day % 365) - MS[m] + 1;
    var date = S.ui === 'pt' ? dom + ' ' + T.pt.months[m] : T.en.months[m] + ' ' + dom;
    return tr('dayOf', { d: Math.min(day + 1, Math.ceil(H / 1440)), t: Math.ceil(H / 1440) }) + ' · ' + date + ', ' + hh + ':' + mm;
  }

  // ---------- controls and scenarios ----------
  function knobStep(K) {
    if (K.pct) return 0.01;
    var span = K.max - K.min;
    return Number.isInteger(K.min) && Number.isInteger(K.max) && span >= 1 ? 1 : span / 100;
  }
  function fmtKnob(K, v) { return K.pct ? fmtPct(v) : fmtNum(v, Number.isInteger(v) ? 0 : 2); }
  function renderControls() {
    var M = S.model, box = $('controls-body');
    if (!M.knobOrder.length) { box.innerHTML = '<p class="muted">' + esc(tr('noControls')) + '</p>'; }
    else {
      box.innerHTML = M.knobOrder.map(function (k) {
        var K = M.knobs[k], v = S.knobs[k];
        return '<div class="knob"><div class="knob-top"><label for="knob-' + k + '">' + esc(dn(k)) + '</label><output id="out-' + k + '">' + esc(fmtKnob(K, v)) + '</output></div>' +
          '<input type="range" id="knob-' + k + '" data-k="' + k + '" min="' + K.min + '" max="' + K.max + '" step="' + knobStep(K) + '" value="' + v + '">' +
          '<div class="knob-range"><span>' + esc(fmtKnob(K, K.min)) + '</span><span>' + esc(fmtKnob(K, K.max)) + '</span></div></div>';
      }).join('');
    }
    var sc = $('scenario-body');
    if (!M.scenarios.length) { sc.parentNode.hidden = true; }
    else {
      sc.parentNode.hidden = false;
      sc.innerHTML = '<button type="button" class="chip-btn" data-sc="-1">' + esc(tr('recipeValues')) + '</button>' +
        M.scenarios.map(function (s, i) { return '<button type="button" class="chip-btn" data-sc="' + i + '">' + esc(s.name) + '</button>'; }).join('');
    }
    markScenario();
  }
  function markScenario() {
    var M = S.model;
    document.querySelectorAll('[data-sc]').forEach(function (b) {
      var i = +b.dataset.sc, target = {};
      M.knobOrder.forEach(function (k) { target[k] = i < 0 ? M.knobs[k].init : (k in M.scenarios[i].sets ? M.scenarios[i].sets[k] : S.knobs[k]); });
      var on = M.knobOrder.every(function (k) { return Math.abs(target[k] - S.knobs[k]) < 1e-9; });
      if (i >= 0) on = on && Object.keys(M.scenarios[i].sets).length > 0;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  var knobTimer = null;
  $('controls-body').addEventListener('input', function (e) {
    var k = e.target.dataset.k;
    if (!k) return;
    S.knobs[k] = +e.target.value;
    $('out-' + k).textContent = fmtKnob(S.model.knobs[k], S.knobs[k]);
    markScenario();
    clearTimeout(knobTimer);
    knobTimer = setTimeout(rebuild, 120);
  });
  $('scenario-body').addEventListener('click', function (e) {
    var b = e.target.closest('[data-sc]');
    if (!b) return;
    applyScenario(+b.dataset.sc);
  });
  function applyScenario(i) {
    var M = S.model;
    M.knobOrder.forEach(function (k) {
      if (i < 0) S.knobs[k] = M.knobs[k].init;
      else if (k in M.scenarios[i].sets) S.knobs[k] = Math.min(M.knobs[k].max, Math.max(M.knobs[k].min, M.scenarios[i].sets[k]));
    });
    renderControls();
    rebuild();
  }

  // ---------- metric cards ----------
  function renderCards(structure) {
    var M = S.model, box = $('metrics-body');
    if (structure || box.children.length !== M.shows.length) {
      box.innerHTML = M.shows.map(function (m, i) {
        return '<div class="card"><div class="card-label">' + esc(metricTitle(m)) + (metricKind(m) ? '<span class="card-kind">' + esc(metricKind(m)) + '</span>' : '') + '</div>' +
          '<div class="card-value" id="mv-' + i + '">–</div><div class="card-live">' + esc(tr('live')) + '</div><div class="card-range" id="mr-' + i + '"></div></div>';
      }).join('');
    }
    var res = S.sim.results();
    M.shows.forEach(function (m, i) {
      $('mv-' + i).textContent = fmtMetric(m, BO.metric(m, res));
      var r = S.range, el = $('mr-' + i);
      if (r && r.done && r.cur) {
        var vs = r.cur[i];
        el.textContent = tr('range', { n: vs.length, a: fmtMetric(m, BO.quant(vs, 0.1)), b: fmtMetric(m, BO.quant(vs, 0.9)), m: fmtMetric(m, BO.quant(vs, 0.5)) });
        el.classList.remove('pending');
      } else if (r) {
        el.textContent = tr('rangeCalc', { d: r.progress || 0, t: r.total || 0 });
        el.classList.add('pending');
      }
    });
  }

  // ---------- multi-seed runs in background workers ----------
  var workers = [], workerSrc = $('engine').textContent;
  (function makeWorkers() {
    var n = Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 2) - 1));
    try {
      var url = URL.createObjectURL(new Blob([workerSrc], { type: 'text/javascript' }));
      for (var i = 0; i < n; i++) { var w = new Worker(url); w.busy = false; workers.push(w); }
    } catch (e) { workers = []; }
  })();
  var jobTimer = null;
  function scheduleJob() { clearTimeout(jobTimer); jobTimer = setTimeout(runJob, 350); }
  function runJob() {
    var M = S.model, id = ++S.job;
    var expected = S.plan.statedPerMin * S.plan.openFrac * S.plan.horizon;
    var nSeeds = expected > 200000 ? 6 : 10;
    var seeds = [];
    for (var i = 0; i < nSeeds; i++) seeds.push(M.seed * 1009 + i * 7919 + 1);
    var configs = [{ key: 'cur', plan: S.plan }];
    M.scenarios.forEach(function (sc, si) {
      var kv = {};
      M.knobOrder.forEach(function (k) { kv[k] = k in sc.sets ? Math.min(M.knobs[k].max, Math.max(M.knobs[k].min, sc.sets[k])) : S.knobs[k]; });
      configs.push({ key: 'sc' + si, plan: SIMLANG.compile(M, kv) });
    });
    var tasks = [];
    configs.forEach(function (c) { seeds.forEach(function (s) { tasks.push({ key: c.key, plan: c.plan, seed: s }); }); });
    var store = {};
    configs.forEach(function (c) { store[c.key] = M.shows.map(function () { return []; }); });
    S.range = { id: id, total: tasks.length, progress: 0, done: false, nSeeds: nSeeds, configs: configs };
    S.compare = null;
    renderCompare();
    var next = 0, finished = 0, shows = M.shows;
    function finish(t, vals) {
      if (S.job !== id) return;
      vals.forEach(function (v, k) { store[t.key][k].push(v[0]); });
      finished++;
      S.range.progress = finished;
      if (store.cur[0] && store.cur[0].length === nSeeds && !S.range.cur) {
        S.range.cur = store.cur.map(function (a) { return a.slice().sort(function (x, y) { return x - y; }); });
        S.range.done = true;
      }
      if (finished === tasks.length) S.compare = store;
      renderCompare();
      renderCards(false);
    }
    function feed(w) {
      if (S.job !== id || next >= tasks.length) { w.busy = false; return; }
      var t = tasks[next++];
      w.busy = true;
      w.onmessage = function (ev) {
        if (ev.data.type !== 'done') return;
        finish(t, ev.data.out[0].vals);
        feed(w);
      };
      w.postMessage({ id: id, configs: [{ key: t.key, plan: t.plan }], seeds: [t.seed], shows: shows });
    }
    if (workers.length) {
      workers.forEach(function (w) {
        if (!w.busy) feed(w);
        else w.onmessage = function (ev) { if (ev.data.type === 'done') feed(w); };
      });
    } else {
      (function step() {
        if (S.job !== id || next >= tasks.length) return;
        var t = tasks[next++], sim = new BO.Sim(t.plan, t.seed, {});
        sim.runUntil(t.plan.horizon);
        var res = sim.results();
        finish(t, shows.map(function (m) { return [BO.metric(m, res)]; }));
        setTimeout(step, 0);
      })();
    }
  }

  function renderCompare() {
    var M = S.model, box = $('compare');
    if (!M.scenarios.length) { box.hidden = true; return; }
    box.hidden = false;
    var r = S.range, cols = [{ key: 'cur', name: tr('current'), i: -1 }].concat(M.scenarios.map(function (s, i) { return { key: 'sc' + i, name: s.name, i: i }; }));
    var head = '<tr><th scope="col"></th>' + cols.map(function (c) {
      return '<th scope="col"><span>' + esc(c.name) + '</span>' + (c.i >= 0 ? '<button type="button" class="link" data-apply="' + c.i + '">' + esc(tr('apply')) + '</button>' : '') + '</th>';
    }).join('') + '</tr>';
    var body = M.shows.map(function (m, k) {
      return '<tr><th scope="row">' + esc(metricTitle(m)) + '</th>' + cols.map(function (c) {
        if (!S.compare) return '<td><span class="pending">…</span></td>';
        var vs = S.compare[c.key][k].slice().sort(function (a, b) { return a - b; });
        return '<td><strong>' + esc(fmtMetric(m, BO.quant(vs, 0.5))) + '</strong><small>' + esc(fmtMetric(m, BO.quant(vs, 0.1))) + ' – ' + esc(fmtMetric(m, BO.quant(vs, 0.9))) + '</small></td>';
      }).join('') + '</tr>';
    }).join('');
    $('compare-note').textContent = S.compare ? tr('compareNote', { n: r.nSeeds }) : tr('rangeCalc', { d: r ? r.progress : 0, t: r ? r.total : 0 });
    $('compare-table').innerHTML = '<thead>' + head + '</thead><tbody>' + body + '</tbody>';
  }
  $('compare').addEventListener('click', function (e) {
    var b = e.target.closest('[data-apply]');
    if (b) applyScenario(+b.dataset.apply);
  });

  // ---------- canvas layout ----------
  var canvas = $('canvas'), ctx = canvas.getContext('2d');
  function computeLayout() {
    var P = S.plan, M = S.model, nodes = {}, order = [], edges = [];
    var depth = {};
    depth.src = 0;
    var entryName = P.entry.e ? P.ends[P.entry.i] : P.steps[P.entry.i].name;
    function tname(t) { return t.e ? P.ends[t.i] : P.steps[t.i].name; }
    // longest path depth over steps, leaving out the edges that go back (rework), drawn as returns under the flow
    var stepDepth = P.steps.map(function () { return 1; }), changed = true, guard = 0;
    while (changed && guard++ < 50) {
      changed = false;
      P.routes.forEach(function (r, i) {
        var ts = r.k === 's' ? [r.to] : r.k === 'b' ? r.tos : r.byAttr.concat([r.other]);
        ts.forEach(function (t) { if (t && !t.e && P.back[i].indexOf(t.i) < 0 && stepDepth[t.i] < stepDepth[i] + 1) { stepDepth[t.i] = stepDepth[i] + 1; changed = true; } });
      });
    }
    var maxD = Math.max.apply(null, stepDepth);
    var cols = [];
    function place(id, type, col, extra) {
      (cols[col] = cols[col] || []).push(id);
      nodes[id] = Object.assign({ id: id, type: type, col: col }, extra || {});
    }
    place('src', 'src', 0);
    P.steps.forEach(function (st, i) { place(st.name, 'step', stepDepth[i], { si: i }); });
    P.ends.forEach(function (n, i) { place('end:' + n, 'end', maxD + 1, { ei: i, name: n }); });
    var totalFlow = P.statedPerMin * P.openFrac || 1;
    function nodeKey(t) { return t.e ? 'end:' + P.ends[t.i] : P.steps[t.i].name; }
    edges.push({ from: 'src', to: nodeKey(P.entry), key: 'src>' + entryName, w: 1, label: '' });
    P.routes.forEach(function (r, i) {
      var from = P.steps[i].name, f = S.flows.inflow[i] / totalFlow;
      if (r.k === 's') edges.push({ from: from, to: nodeKey(r.to), key: from + '>' + tname(r.to), w: f, label: '' });
      else if (r.k === 'b') r.tos.forEach(function (t, k) { edges.push({ from: from, to: nodeKey(t), key: from + '>' + tname(t), w: f * r.ps[k], label: fmtPct(r.ps[k]) }); });
      else {
        var mr = M.routes[from];
        M.mix.values.forEach(function (v, a) {
          var t = r.byAttr[a];
          if (t) edges.push({ from: from, to: nodeKey(t), key: from + '>' + tname(t), w: f * M.mix.pcts[a], label: dn(v) });
        });
        if (r.other) {
          var share = 0;
          M.mix.values.forEach(function (v, a) { if (!r.byAttr[a]) share += M.mix.pcts[a]; });
          edges.push({ from: from, to: nodeKey(r.other), key: from + '>' + tname(r.other), w: f * share, label: tr('otherwise') });
        }
      }
      var ab = P.abandon[i];
      if (ab) edges.push({ from: from, to: nodeKey(ab.to), key: from + '>' + tname(ab.to) + '!', w: 0, label: tr('after', { x: fmtDur(ab.after) }), ab: true });
    });
    edges.forEach(function (e) { var a = nodes[e.from], b = nodes[e.to]; if (!e.ab && a && b && a.type === 'step' && b.type === 'step' && P.back[a.si].indexOf(b.si) >= 0) e.back = true; });
    // merge duplicate keys (two attribute values routed to the same target)
    var merged = {}, list = [];
    edges.forEach(function (e) {
      if (merged[e.key]) { merged[e.key].w += e.w; merged[e.key].label = [merged[e.key].label, e.label].filter(Boolean).join(', '); }
      else { merged[e.key] = e; list.push(e); }
    });
    S.layout = { nodes: nodes, cols: cols, edges: list, byKey: merged, backs: list.filter(function (e) { return e.back; }).length };
    sizeCanvas();
  }
  function sizeCanvas() {
    if (!S.layout) return;
    var L = S.layout, wrap = $('canvas-wrap'), nCols = L.cols.length;
    var maxRows = Math.max.apply(null, L.cols.map(function (c) { return c.length; }));
    var W = Math.max(wrap.clientWidth, nCols * 140), rowH = 118, under = L.backs ? 26 + 18 * L.backs : 0, H = Math.max(240, maxRows * rowH + 40 + under);
    var dpr = window.devicePixelRatio || 1;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var colW = W / nCols;
    L.W = W; L.H = H; L.under = under;
    L.cols.forEach(function (ids, c) {
      var off = (H - under - ids.length * rowH) / 2;
      ids.forEach(function (id, r) {
        var n = L.nodes[id];
        n.x = colW * (c + 0.5);
        n.y = off + rowH * (r + 0.5) - (n.type === 'step' && S.plan.steps[n.si].pool >= 0 ? 14 : 0);
        n.w = Math.min(n.type === 'step' ? 170 : 184, colW - 24);
        n.h = n.type === 'step' ? 54 : 46;
      });
    });
  }
  window.addEventListener('resize', function () { sizeCanvas(); });

  function bez(e) {
    var a = S.layout.nodes[e.from], b = S.layout.nodes[e.to], dy = e.ab ? 12 : 0;
    if (e.back) {
      // a return: down from the step that sends it back, along the space under the flow, up into the step it goes to
      var k = S.layout.edges.filter(function (x) { return x.back; }).indexOf(e), yb = S.layout.H - S.layout.under + 14 + 18 * k;
      return [a.x, a.y + a.h / 2, a.x, yb, b.x, yb, b.x, b.y + b.h / 2];
    }
    var x1 = a.x + a.w / 2, y1 = a.y + dy, x2 = b.x - b.w / 2, y2 = b.y + (e.ab ? 0 : 0), dx = (x2 - x1) * 0.5;
    if (e.ab) { y1 = a.y + a.h / 2 - 8; }
    return [x1, y1, x1 + dx, y1, x2 - dx, y2, x2, y2];
  }
  function bpt(p, t) {
    var u = 1 - t;
    return [u * u * u * p[0] + 3 * u * u * t * p[2] + 3 * u * t * t * p[4] + t * t * t * p[6],
      u * u * u * p[1] + 3 * u * u * t * p[3] + 3 * u * t * t * p[5] + t * t * t * p[7]];
  }
  function rrect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function fit(text, maxW) {
    if (ctx.measureText(text).width <= maxW) return text;
    while (text.length > 1 && ctx.measureText(text + '…').width > maxW) text = text.slice(0, -1);
    return text + '…';
  }
  var FONT = getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim() || 'sans-serif';
  var MONO = getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim() || 'monospace';

  function draw() {
    var L = S.layout, C = S.colors, P = S.plan;
    if (!L) return;
    ctx.clearRect(0, 0, L.W, L.H);
    ctx.fillStyle = C.stage; ctx.fillRect(0, 0, L.W, L.H);
    // edges
    L.edges.forEach(function (e) {
      var p = bez(e);
      ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.bezierCurveTo(p[2], p[3], p[4], p[5], p[6], p[7]);
      ctx.strokeStyle = e.ab ? C.crit : C.edge;
      ctx.globalAlpha = e.ab ? 0.75 : 1;
      ctx.lineWidth = e.ab ? 1.25 : 1 + 4 * Math.min(1, e.w);
      ctx.setLineDash(e.ab ? [4, 4] : []);
      ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
    });
    // particles
    S.particles.forEach(function (pt) {
      var e = L.byKey[pt.key];
      if (!e) return;
      var q = bpt(bez(e), pt.s);
      ctx.beginPath(); ctx.arc(q[0], q[1], 3, 0, 6.2832);
      ctx.fillStyle = pt.c; ctx.fill();
    });
    L.edges.forEach(function (e) {
      if (!e.label) return;
      var m = bpt(bez(e), 0.5);
      ctx.font = '500 11px ' + FONT;
      var tw = ctx.measureText(e.label).width + 10;
      ctx.fillStyle = C.stage; rrect(m[0] - tw / 2, m[1] - 9, tw, 18, 9); ctx.fill();
      ctx.lineWidth = 1; ctx.strokeStyle = C.line; ctx.stroke();
      ctx.fillStyle = e.ab ? C.crit : C.muted; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(e.label, m[0], m[1] + 0.5);
    });
    var res = S.sim, cats = C.cats;
    Object.keys(L.nodes).forEach(function (id) {
      var n = L.nodes[id], x = n.x - n.w / 2, y = n.y - n.h / 2;
      ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
      if (n.type === 'src') {
        rrect(x, y, n.w, n.h, n.h / 2); ctx.fillStyle = C.surface; ctx.fill();
        ctx.lineWidth = 1.25; ctx.strokeStyle = C.accent; ctx.stroke();
        ctx.fillStyle = C.ink; ctx.font = '600 12.5px ' + FONT;
        ctx.fillText(fit(tr('arrivals') + ' · ' + dn(S.model.arrival.item), n.w - 20), n.x, n.y - 3);
        ctx.fillStyle = C.muted; ctx.font = '11px ' + MONO;
        ctx.fillText(fmtNum(res.arrivals, 0), n.x, n.y + 13);
        return;
      }
      if (n.type === 'end') {
        var cnt = res.ends[n.ei], isAb = L.edges.some(function (e) { return e.ab && e.to === id; });
        rrect(x, y, n.w, n.h, 8); ctx.fillStyle = C.surface; ctx.fill();
        ctx.lineWidth = 1; ctx.strokeStyle = isAb ? C.crit : C.line; ctx.stroke();
        ctx.fillStyle = isAb ? C.crit : C.ink; ctx.font = '600 12.5px ' + FONT;
        if (ctx.measureText(dn(n.name)).width > n.w - 16) ctx.font = '600 11px ' + FONT;
        ctx.fillText(fit(dn(n.name), n.w - 12), n.x, n.y - 3);
        ctx.fillStyle = C.muted; ctx.font = '11px ' + MONO;
        ctx.fillText(fmtNum(cnt, 0), n.x, n.y + 13);
        return;
      }
      var st = P.steps[n.si], Sst = res.steps[n.si];
      rrect(x, y, n.w, n.h, 8); ctx.fillStyle = C.surface; ctx.fill();
      ctx.lineWidth = st.pool >= 0 ? 1.5 : 1; ctx.strokeStyle = st.pool >= 0 ? C.ink : C.line; ctx.stroke();
      ctx.fillStyle = C.ink; ctx.font = '600 13px ' + FONT;
      ctx.fillText(fit(dn(st.name), n.w - 16), n.x, y + 22);
      ctx.font = '11px ' + MONO; ctx.fillStyle = C.muted;
      if (st.pool >= 0) {
        var pl = res.pools[st.pool], qty = P.pools[st.pool].qty;
        ctx.fillText(fit(pl.open ? tr('busy', { b: fmtNum(pl.busy, 0), q: fmtNum(qty, 0) }) : tr('offShift') + ' · ' + fmtNum(qty, 0), n.w - 16), n.x, y + 39);
        // utilization bar along the bottom edge
        var u = qty ? Math.min(1, pl.busy / qty) : 0;
        ctx.fillStyle = C.line; ctx.fillRect(x + 8, y + n.h - 7, n.w - 16, 3);
        ctx.fillStyle = C.accent; ctx.fillRect(x + 8, y + n.h - 7, (n.w - 16) * u, 3);
        // queue as dots under the box, colored by attribute
        var qn = Sst.qn, shown = Math.min(qn, 36), perRow = 12, sp = 8, dx0 = n.x - (Math.min(shown, perRow) - 1) * sp / 2;
        var colorsSeq = [];
        if (shown) {
          var tot = Sst.qAttr.reduce(function (a, b) { return a + b; }, 0) || 1, acc = 0, k = 0;
          Sst.qAttr.forEach(function (c, a) { acc += c; var upto = Math.round(acc / tot * shown); while (k < upto) { colorsSeq.push(cats[a % cats.length]); k++; } });
          while (colorsSeq.length < shown) colorsSeq.push(cats[0]);
        }
        for (var d = 0; d < shown; d++) {
          var row = Math.floor(d / perRow), col = d % perRow;
          ctx.beginPath(); ctx.arc(dx0 + col * sp, y + n.h + 10 + row * sp, 2.8, 0, 6.2832);
          ctx.fillStyle = S.model.mix ? colorsSeq[d] : C.accent; ctx.fill();
        }
        ctx.fillStyle = qn > 0 ? C.ink : C.muted; ctx.font = '11px ' + FONT;
        ctx.fillText(qn > 0 ? tr('waiting', { n: fmtNum(qn, 0) }) : tr('noQueue'), n.x, y + n.h + 14 + (shown ? Math.ceil(shown / perRow) * sp + 4 : 0));
      } else {
        var tm = st.time;
        ctx.fillText((tm.k === 'e' ? '~' : '') + (tm.k === 'u' ? fmtDur(tm.a) + '–' + fmtDur(tm.b) : fmtDur(tm.a)), n.x, y + 39);
      }
    });
  }

  // ---------- legend ----------
  function renderLegend() {
    var M = S.model, box = $('legend');
    if (!M || !M.mix) { box.innerHTML = ''; return; }
    box.innerHTML = '<span class="legend-title">' + esc(dn(M.mix.attr)) + '</span>' + M.mix.values.map(function (v, a) {
      return '<span class="legend-item"><i style="background:var(--cat' + (a % 6 + 1) + ')"></i>' + esc(dn(v)) + ' · ' + esc(fmtPct(M.mix.pcts[a])) + '</span>';
    }).join('');
  }

  // ---------- animation loop ----------
  var reduced = matchMedia('(prefers-reduced-motion: reduce)');
  var last = performance.now();
  function frame(now) {
    var dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    if (S.sim && S.plan) {
      if (S.playing && !S.sim.finished) {
        var simPerSec = S.plan.horizon / 30 * S.speed;
        S.simT = Math.min(S.plan.horizon, S.simT + dt * simPerSec);
        S.sim.runUntil(S.simT);
        var moves = S.sim.takeMoves();
        if (!reduced.matches) {
          var perRealSec = S.plan.statedPerMin * S.plan.openFrac * simPerSec, pf = Math.min(1, 45 / Math.max(1e-9, perRealSec));
          Object.keys(moves).forEach(function (key) {
            if (!S.layout.byKey[key]) return;
            var acc = S.acc[key] || (S.acc[key] = new Array(moves[key].length).fill(0)), spawned = 0;
            moves[key].forEach(function (c, a) {
              acc[a] += c * pf;
              while (acc[a] >= 1 && spawned < 8) {
                acc[a] -= 1; spawned++;
                S.particles.push({ key: key, s: Math.random() * 0.1, c: S.model.mix ? S.colors.cats[a % 6] : (key.slice(-1) === '!' ? S.colors.crit : S.colors.accent) });
              }
              if (acc[a] > 4) acc[a] = 4;
            });
          });
        }
        if (S.sim.finished) { S.playing = false; updatePlay(); }
      }
      if (!reduced.matches) {
        var speed = S.playing ? 1.1 : 0;
        S.particles.forEach(function (p) { p.s += dt * speed; });
        S.particles = S.particles.filter(function (p) { return p.s < 1; });
      }
      draw();
      $('bar').style.width = (S.simT / S.plan.horizon * 100) + '%';
      $('clock-text').textContent = S.sim.finished ? tr('finished') + ' · ' + clockText() : clockText();
      var shape = BO.shapeAt(S.plan.arrival, Math.min(S.simT, S.plan.horizon - 1e-6)), pk = $('peak');
      if (shape === 0) { pk.hidden = false; pk.textContent = tr('closed'); pk.className = 'chip peak closed'; }
      else if (shape > 1.0001) { pk.hidden = false; pk.textContent = tr('peak', { f: fmtNum(shape, 1) }); pk.className = 'chip peak'; }
      else pk.hidden = true;
      if (now - S.lastCards > 250) { S.lastCards = now; renderCards(false); }
    }
    requestAnimationFrame(frame);
  }

  // ---------- screen language ----------
  function applyUi() {
    document.documentElement.lang = S.ui === 'pt' ? 'pt-BR' : 'en';
    document.querySelectorAll('[data-i18n]').forEach(function (el) { el.textContent = tr(el.dataset.i18n); });
    $('ui-en').setAttribute('aria-pressed', S.ui === 'en' ? 'true' : 'false');
    $('ui-pt').setAttribute('aria-pressed', S.ui === 'pt' ? 'true' : 'false');
    try { localStorage.setItem('bo-ui', S.ui); } catch (e) {}
    if (S.model) {
      $('translate').textContent = tr('translateTo', { x: S.model.lang === 'en' ? 'pt-BR' : 'en' });
      renderHeader(); renderControls(); renderCards(true); renderCompare(); renderValidator(); renderLegend(); updatePlay(); computeLayout();
    }
  }
  $('ui-en').addEventListener('click', function () { S.ui = 'en'; applyUi(); });
  $('ui-pt').addEventListener('click', function () { S.ui = 'pt'; applyUi(); });

  setSource(EXAMPLES[0].src, false);
  applyUi();
  requestAnimationFrame(frame);
})();

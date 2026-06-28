/* app.js — orchestration. Talks to the FastAPI backend, builds the controls,
   drives the mercury gauge, renders analytics, the explorer, and news.
   No mock data anywhere: every value comes from /api/*. */

const API = '';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const fmt = (n, d = 2) => Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

const TIER_COLORS = {
  exceptional: 'var(--t-exceptional)', excellent: 'var(--t-excellent)',
  good: 'var(--t-good)', moderate: 'var(--t-moderate)', high: 'var(--t-high)',
};

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

/* ---------------- NAV ---------------- */
function initNav() {
  const nav = $('#nav');
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 30);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  const links = $$('.nav-link');
  const sections = links.map(l => $(l.getAttribute('href')));
  const spy = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        const id = '#' + e.target.id;
        links.forEach(l => l.classList.toggle('active', l.getAttribute('href') === id));
      }
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  sections.forEach(s => s && spy.observe(s));
}

/* ---------------- reveal on scroll ---------------- */
function initReveal() {
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  $$('.reveal').forEach(el => io.observe(el));
}

/* ---------------- CONTROLS ---------------- */
let OPTIONS = null;

function buildControls() {
  const r = OPTIONS.ranges;
  const sel = (id, label, items) => `
    <div class="field">
      <div class="field-label"><span>${label}</span></div>
      <div class="select-wrap"><select class="select" id="${id}">
        ${items.map(o => `<option value="${o}">${o}</option>`).join('')}
      </select></div>
    </div>`;
  const slider = (id, label, cfg, unit) => `
    <div class="field">
      <div class="field-label"><span>${label}</span><span class="val"><span id="${id}Val">${cfg.default}</span>${unit}</span></div>
      <input class="range" type="range" id="${id}" min="${cfg.min}" max="${cfg.max}" step="${cfg.step}" value="${cfg.default}" />
    </div>`;

  $('#controls').innerHTML =
    sel('vehicle_class', 'Vehicle class', OPTIONS.vehicle_classes) +
    `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
       ${sel('transmission', 'Transmission', OPTIONS.transmissions)}
       ${sel('fuel_type', 'Fuel type', OPTIONS.fuel_types)}
     </div>` +
    slider('engine_size', 'Engine size', r.engine_size, ' L') +
    `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
       ${slider('cylinders', 'Cylinders', r.cylinders, '')}
       ${slider('co2_rating', 'CO₂ rating', r.co2_rating, ' / 10')}
     </div>`;

  // sensible defaults
  const setSel = (id, v) => { const el = $('#' + id); if ([...el.options].some(o => o.value === v)) el.value = v; };
  setSel('vehicle_class', 'SUV: Small');
  setSel('fuel_type', 'Gasoline');
  setSel('transmission', 'Automatic');

  // slider fill + live value
  $$('.range').forEach(rng => {
    const upd = () => {
      const pct = ((rng.value - rng.min) / (rng.max - rng.min)) * 100;
      rng.style.setProperty('--fill', pct + '%');
      const lab = $('#' + rng.id + 'Val'); if (lab) lab.textContent = rng.value;
    };
    upd();
    rng.addEventListener('input', upd);
  });
}

/* ---------------- GAUGE ---------------- */
const GAUGE_MAX = 30; // L/100km full-scale

function buildGaugeTicks() {
  const ticks = [5, 10, 15, 20, 25];
  // position by percentage from the bottom so it scales with the tall tube
  $('#gaugeTicks').innerHTML = ticks.map(t => {
    const pctFromBottom = (t / GAUGE_MAX) * 100;
    return `<div class="gauge-tick" style="bottom:${pctFromBottom}%"><span>${t}</span></div>`;
  }).join('');
  // rising bubbles
  const bubbles = Array.from({ length: 9 }, () => {
    const left = 10 + Math.random() * 80;
    const dur = 4 + Math.random() * 4;
    const delay = Math.random() * 5;
    const size = 4 + Math.random() * 5;
    return `<span class="bub" style="left:${left}%;width:${size}px;height:${size}px;--dur:${dur}s;--delay:${delay}s"></span>`;
  }).join('');
  $('#gaugeBubbles').innerHTML = bubbles;
}

function renderPrediction(res) {
  const pct = Math.min(100, (res.consumption_l_per_100km / GAUGE_MAX) * 100);
  $('#gaugeFluid').style.height = pct + '%';
  const tier = res.efficiency.tier;
  const col = TIER_COLORS[tier];
  $('#gaugeFluid').style.background =
    `linear-gradient(180deg, ${col} 0%, rgba(195,200,212,0.88) 42%, rgba(74,77,87,0.96) 100%)`;
  $('#gaugeMpg').textContent = res.consumption_mpg ? `${res.consumption_mpg} mpg` : '';

  // big number floating inside the tank
  const inline = $('#gaugeInline');
  inline.innerHTML = `<div class="big chrome-text">${fmt(res.consumption_l_per_100km)}</div><div class="u">L / 100 KM</div>`;
  inline.classList.add('show');

  $('#gaugeReadout').innerHTML = `
    <div class="tier-pill"><span class="swatch" style="background:${col}"></span>${res.efficiency.label} efficiency</div>
    <div class="tier-note">${res.efficiency.note}</div>
    <div class="tier-context">more efficient than ${fmt(100 - res.fleet_percentile, 0)}% of ${res.comparison_segment || 'the fleet'}</div>`;
}

async function doPredict() {
  const btn = $('#predictBtn');
  const payload = {
    engine_size: parseFloat($('#engine_size').value),
    cylinders: parseInt($('#cylinders').value, 10),
    co2_rating: parseFloat($('#co2_rating').value),
    vehicle_class: $('#vehicle_class').value,
    transmission: $('#transmission').value,
    fuel_type: $('#fuel_type').value,
  };
  btn.disabled = true; btn.textContent = 'Calculating…'; $('#panelStatus').textContent = 'computing';
  try {
    const res = await api('/api/predict', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    renderPrediction(res);
    $('#panelStatus').textContent = 'done';
  } catch (e) {
    $('#gaugeReadout').innerHTML = `<div class="gauge-empty">Couldn't reach the model. ${e.message}</div>`;
    $('#panelStatus').textContent = 'error';
  } finally {
    btn.disabled = false; btn.textContent = 'Calculate consumption';
  }
}

/* ---------------- ANALYTICS ---------------- */
function renderKPIs(s) {
  const tiles = [
    { n: s.total_vehicles.toLocaleString(), l: 'vehicles analysed' },
    { n: fmt(s.avg_consumption), l: 'avg L/100 km', sub: `median ${fmt(s.median_consumption)}` },
    { n: fmt(s.car_avg_consumption), l: 'avg for cars', sub: 'excl. 2-wheelers' },
    { n: s.n_brands ?? '—', l: 'brands' },
    { n: s.n_classes, l: 'vehicle classes' },
    { n: s.electric_share_pct + '%', l: 'electric share' },
    { n: fmt(s.avg_engine_size, 1) + ' L', l: 'avg engine size' },
    { n: fmt(s.avg_co2_rating, 1), l: 'avg CO₂ rating' },
  ];
  $('#kpiGrid').innerHTML = tiles.map(t => `
    <div class="kpi glass">
      <div class="n chrome-text">${t.n}</div>
      <div class="l">${t.l}</div>
      ${t.sub ? `<div class="sub">${t.sub}</div>` : ''}
    </div>`).join('');
}

function chartCard(title, sub, svg, wide = false) {
  return `<div class="chart-card glass ${wide ? 'chart-wide' : ''}">
    <h4>${title}</h4><div class="sub">${sub}</div>
    <div class="chart-canvas">${svg}</div></div>`;
}

function renderAnalytics(a) {
  renderKPIs(a.summary);
  $('#chartGrid').innerHTML =
    chartCard('Consumption distribution', 'How combined L/100 km is spread across the fleet',
      Charts.histogram(a.distribution)) +
    chartCard('Mean consumption by fuel', 'Average combined consumption per fuel type',
      Charts.hbar(a.by_fuel, { valueSuffix: ' L', colorByFuel: true })) +
    chartCard('Most efficient classes', 'Lowest mean consumption (classes with ≥3 vehicles)',
      Charts.hbar(a.by_class, { valueSuffix: ' L' })) +
    chartCard('Consumption by cylinder count', 'Mean L/100 km as cylinders increase',
      Charts.line(a.by_cylinders)) +
    chartCard('Engine size vs consumption', 'Each point is a vehicle; dashed line is the least-squares trend',
      Charts.scatter(a.engine_scatter), true) +
    chartCard('Feature correlation', 'Pearson correlation among numeric features and the target',
      Charts.heatmap(a.correlation));

  $('#effList').innerHTML = a.most_efficient.map(v => `
    <div class="eff-row">
      <div class="name">${v.brand} <span>${v.model}</span></div>
      <div class="meta">${v.vehicle_class}</div>
      <div class="meta">${v.fuel} · ${fmt(v.engine, 1)}L</div>
      <div class="num">${fmt(v.consumption)}</div>
    </div>`).join('');
}

/* ---------------- EXPLORER ---------------- */
const EX = { page: 1, page_size: 25, search: '', vehicle_class: '', fuel: '', sort_by: 'consumption', sort_dir: 'asc', total: 0, pages: 1 };
let exDebounce;

async function loadDataset() {
  const q = new URLSearchParams({
    page: EX.page, page_size: EX.page_size, search: EX.search,
    vehicle_class: EX.vehicle_class, fuel: EX.fuel, sort_by: EX.sort_by, sort_dir: EX.sort_dir,
  });
  const d = await api('/api/dataset?' + q.toString());
  EX.total = d.total; EX.pages = d.pages;

  // populate facet filters once
  const fc = $('#filterClass'), ff = $('#filterFuel');
  if (fc.options.length <= 1) {
    d.facets.vehicle_classes.forEach(c => fc.add(new Option(c, c)));
    d.facets.fuels.forEach(f => ff.add(new Option(f, f)));
  }

  $('#dataBody').innerHTML = d.rows.length ? d.rows.map(r => `
    <tr>
      <td>${r.brand}</td>
      <td>${r.model}</td>
      <td><span class="tag">${r.vehicle_class}</span></td>
      <td>${r.fuel}</td>
      <td class="num">${fmt(r.engine, 1)}</td>
      <td class="num">${r.cylinders}</td>
      <td class="num">${r.co2_rating}</td>
      <td class="num" style="color:var(--chrome-1)">${fmt(r.consumption)}</td>
    </tr>`).join('') : `<tr><td colspan="8"><div class="empty-state">No vehicles match these filters.</div></td></tr>`;

  const from = d.total ? (EX.page - 1) * EX.page_size + 1 : 0;
  const to = Math.min(EX.page * EX.page_size, d.total);
  $('#pagerInfo').textContent = `${from}–${to} of ${d.total}`;
  $('#prevPage').disabled = EX.page <= 1;
  $('#nextPage').disabled = EX.page >= EX.pages;

  $$('#dataTable thead th').forEach(th => {
    const k = th.dataset.sort;
    th.classList.toggle('sorted', k === EX.sort_by);
    th.textContent = th.textContent.replace(/ [▲▼]$/, '') + (k === EX.sort_by ? (EX.sort_dir === 'asc' ? ' ▲' : ' ▼') : '');
  });
}

function initExplorer() {
  $('#search').addEventListener('input', (e) => {
    clearTimeout(exDebounce);
    exDebounce = setTimeout(() => { EX.search = e.target.value; EX.page = 1; loadDataset(); }, 250);
  });
  $('#filterClass').addEventListener('change', e => { EX.vehicle_class = e.target.value; EX.page = 1; loadDataset(); });
  $('#filterFuel').addEventListener('change', e => { EX.fuel = e.target.value; EX.page = 1; loadDataset(); });
  $('#prevPage').addEventListener('click', () => { if (EX.page > 1) { EX.page--; loadDataset(); } });
  $('#nextPage').addEventListener('click', () => { if (EX.page < EX.pages) { EX.page++; loadDataset(); } });
  $$('#dataTable thead th').forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.sort;
    if (EX.sort_by === k) EX.sort_dir = EX.sort_dir === 'asc' ? 'desc' : 'asc';
    else { EX.sort_by = k; EX.sort_dir = 'asc'; }
    EX.page = 1; loadDataset();
  }));
}

/* ---------------- NEWS (right rail) ---------------- */
async function loadNews() {
  const body = $('#newsRailBody');
  try {
    const d = await api('/api/news');
    if (!d.items.length) {
      body.innerHTML = `<div class="empty-state" style="padding:24px 0">No headlines right now.</div>`;
      $('#newsBadge').classList.add('snapshot');
      return;
    }
    body.innerHTML = d.items.map(n => `
      <a class="news-rail-item" href="${n.link}" target="_blank" rel="noopener">
        <h6>${n.title}</h6>
        ${n.published ? `<div class="date">${n.published}</div>` : ''}
      </a>`).join('');
  } catch {
    body.innerHTML = `<div class="empty-state" style="padding:24px 0">Couldn't load headlines.</div>`;
    $('#newsBadge').classList.add('snapshot');
  }
}

/* ---------------- FUEL RATES (left rail) ---------------- */
function fmtUpdated(iso) {
  // Render an ISO timestamp as a friendly local "Last updated" string.
  try {
    const dt = new Date(iso);
    if (isNaN(dt)) return iso;
    return dt.toLocaleString(undefined, {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

async function loadFuelRates() {
  const body = $('#ratesBody');
  try {
    const d = await api('/api/fuel-rates');
    const badge = $('#ratesBadge');
    if (!d.live) {
      badge.classList.add('snapshot');
      $('#ratesBadgeText').textContent = 'snapshot';
    } else {
      badge.classList.remove('snapshot');
      $('#ratesBadgeText').textContent = 'live';
    }
    const legend = `<div class="rates-legend">
        <span><span class="sw" style="background:var(--chrome-1)"></span>Petrol</span>
        <span><span class="sw" style="background:var(--accent)"></span>Diesel</span>
      </div>`;
    const rows = d.rows.map(r => `
      <div class="rate-row${r.estimated ? ' est' : ''}"${r.estimated ? ' title="estimated — live source missed this city"' : ''}>
        <span class="city">${r.city}</span>
        <span class="p">${r.petrol != null ? '₹' + fmt(r.petrol) : '—'}</span>
        <span class="d">${r.diesel != null ? '₹' + fmt(r.diesel) : '—'}</span>
      </div>`).join('');
    body.innerHTML = legend + rows;

    // Clear "Last updated" + source provenance, exactly as fetched.
    const sourceLabel = d.source === 'indianapi.in' ? 'indianapi.in'
      : d.source === 'newsrain.in' ? 'newsrain.in'
      : 'snapshot';
    $('#ratesFoot').innerHTML = d.live
      ? `Last updated ${fmtUpdated(d.last_updated)}<br>source: ${sourceLabel} · prices as of ${d.as_of}`
      : `Snapshot · prices as of ${d.as_of}<br>live source unavailable`;
  } catch {
    body.innerHTML = `<div class="empty-state" style="padding:24px 0">Rates unavailable.</div>`;
    $('#ratesBadge').classList.add('snapshot');
  }
}

/* ---------------- LOADER (gas fill-up) ---------------- */
function runLoader() {
  const pctEl = $('#loaderPct');
  if (!pctEl) return Promise.resolve();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const dur = reduced ? 300 : 2200;
  const start = performance.now();
  return new Promise(resolve => {
    function tick(now) {
      const p = Math.min(1, (now - start) / dur);
      pctEl.textContent = Math.round(p * 100) + '%';
      if (p < 1) requestAnimationFrame(tick);
      else resolve();
    }
    requestAnimationFrame(tick);
  });
}

function hideLoader() {
  const l = $('#loader');
  if (l) { l.classList.add('hide'); setTimeout(() => l.remove(), 900); }
}

/* ---------------- BOOT ---------------- */
async function boot() {
  initNav(); initReveal();
  buildGaugeTicks();

  // kick off the loader animation and data fetches in parallel
  const loaderDone = runLoader();

  // health → nav metric
  try {
    const h = await api('/api/health');
    if (h.metrics && h.metrics.test_r2 != null) {
      $('#navMetricText').textContent = `R² ${h.metrics.test_r2} · MAE ${h.metrics.test_mae}`;
    } else { $('#navMetricText').textContent = 'model ready'; }
  } catch { $('#navMetricText').textContent = 'offline'; }

  // options → controls + hero meta
  try {
    OPTIONS = await api('/api/options');
    buildControls();
    $('#predictBtn').addEventListener('click', doPredict);
  } catch (e) {
    $('#controls').innerHTML = `<div class="empty-state">Couldn't load configuration options.</div>`;
  }

  // analytics
  try {
    const a = await api('/api/analytics');
    renderAnalytics(a);
    $('#heroMeta').innerHTML = `
      <div class="stat"><div class="n">${a.summary.total_vehicles.toLocaleString()}</div><div class="l">vehicles</div></div>
      <div class="stat"><div class="n">${a.summary.n_brands}</div><div class="l">brands</div></div>
      <div class="stat"><div class="n">${fmt(a.summary.car_avg_consumption)}</div><div class="l">avg L/100km (cars)</div></div>`;
  } catch (e) {
    $('#chartGrid').innerHTML = `<div class="empty-state">Analytics unavailable.</div>`;
  }

  // explorer + rails
  initExplorer();
  loadDataset();
  loadFuelRates();
  loadNews();

  // dismiss loader once the fill animation has played
  await loaderDone;
  hideLoader();
}

document.addEventListener('DOMContentLoaded', boot);

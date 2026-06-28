/* charts.js — minimal bespoke SVG charts (no external libs).
   Each returns an SVG string sized to its container; styling inherits the
   chrome palette. Tooltips are handled by lightweight <title> + hover JS. */

const Charts = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const COL = {
    chrome1: '#e8eaf0', chrome3: '#9aa0ad', chrome5: '#4a4d57',
    accent: '#8fb4d9', grid: 'rgba(220,228,245,0.08)', ink: '#aab0be', mute: '#6c7280',
  };
  const FUEL_COL = {
    Gasoline: '#c3c8d4', Diesel: '#8fb4d9', Electric: '#9fe3c4', Ethanol: '#e8d4a0',
  };

  const esc = (s) => String(s).replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));

  function frame(w, h, pad) {
    return { w, h, pad, iw: w - pad.l - pad.r, ih: h - pad.t - pad.b };
  }

  /* ---- horizontal bars (by class / by fuel) ---- */
  function hbar(data, { w = 520, valueSuffix = '', colorByFuel = false } = {}) {
    const pad = { l: 150, r: 56, t: 8, b: 8 };
    const rowH = 30, gap = 8;
    const h = data.labels.length * (rowH + gap) + pad.t + pad.b;
    const f = frame(w, h, pad);
    const max = Math.max(...data.values) * 1.08;
    let bars = '';
    data.labels.forEach((lab, i) => {
      const y = pad.t + i * (rowH + gap);
      const bw = (data.values[i] / max) * f.iw;
      const col = colorByFuel ? (FUEL_COL[lab] || COL.chrome3) : COL.chrome3;
      const gid = `g${i}_${Math.random().toString(36).slice(2, 6)}`;
      bars += `
        <defs><linearGradient id="${gid}" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stop-color="${col}" stop-opacity="0.35"/>
          <stop offset="1" stop-color="${col}" stop-opacity="0.95"/>
        </linearGradient></defs>
        <text x="${pad.l - 12}" y="${y + rowH / 2}" text-anchor="end" dominant-baseline="middle" font-size="12.5" fill="${COL.ink}" font-family="Inter">${esc(lab)}</text>
        <rect x="${pad.l}" y="${y}" width="${f.iw}" height="${rowH}" rx="6" fill="${COL.grid}"/>
        <rect class="bar-anim" x="${pad.l}" y="${y}" width="${bw}" height="${rowH}" rx="6" fill="url(#${gid})">
          <title>${esc(lab)}: ${data.values[i]}${valueSuffix}${data.counts ? ' · n=' + data.counts[i] : ''}</title>
        </rect>
        <text x="${pad.l + bw + 8}" y="${y + rowH / 2}" dominant-baseline="middle" font-size="12" fill="${COL.chrome1}" font-family="JetBrains Mono">${data.values[i]}</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" preserveAspectRatio="xMidYMid meet">${bars}</svg>`;
  }

  /* ---- histogram (distribution) ---- */
  function histogram(data, { w = 520, h = 240 } = {}) {
    const pad = { l: 40, r: 16, t: 14, b: 34 };
    const f = frame(w, h, pad);
    const max = Math.max(...data.y) * 1.1;
    const n = data.y.length;
    const bw = f.iw / n;
    let bars = '', axis = '';
    data.y.forEach((v, i) => {
      const bh = (v / max) * f.ih;
      const x = pad.l + i * bw;
      const y = pad.t + f.ih - bh;
      bars += `<rect x="${x + 1}" y="${y}" width="${bw - 2}" height="${bh}" rx="2" fill="${COL.chrome3}" fill-opacity="${0.4 + 0.5 * (v / max)}"><title>${data.x[i]} L/100km · ${v} vehicles</title></rect>`;
    });
    // mean line
    const xr = [Math.min(...data.x), Math.max(...data.x)];
    const meanX = pad.l + ((data.mean - xr[0]) / (xr[1] - xr[0])) * f.iw;
    const medX = pad.l + ((data.median - xr[0]) / (xr[1] - xr[0])) * f.iw;
    axis += `<line x1="${meanX}" x2="${meanX}" y1="${pad.t}" y2="${pad.t + f.ih}" stroke="${COL.accent}" stroke-width="1.4" stroke-dasharray="4 3"/>
             <text x="${meanX + 5}" y="${pad.t + 12}" font-size="10" fill="${COL.accent}" font-family="JetBrains Mono">mean ${data.mean}</text>`;
    // x ticks
    [0, 0.5, 1].forEach(t => {
      const x = pad.l + t * f.iw;
      const val = (xr[0] + t * (xr[1] - xr[0])).toFixed(0);
      axis += `<text x="${x}" y="${h - 12}" text-anchor="middle" font-size="10" fill="${COL.mute}" font-family="JetBrains Mono">${val}</text>`;
    });
    axis += `<text x="${pad.l}" y="${h - 12}" text-anchor="start" font-size="9.5" fill="${COL.mute}" font-family="Inter" opacity="0">L/100km</text>`;
    return `<svg viewBox="0 0 ${w} ${h}" width="100%">${bars}${axis}</svg>`;
  }

  /* ---- scatter (engine vs consumption) ---- */
  function scatter(data, { w = 520, h = 260 } = {}) {
    const pad = { l: 42, r: 16, t: 14, b: 34 };
    const f = frame(w, h, pad);
    const xs = data.points.map(p => p.x), ys = data.points.map(p => p.y);
    const xr = [Math.min(...xs), Math.max(...xs)], yr = [0, Math.max(...ys) * 1.05];
    const X = v => pad.l + ((v - xr[0]) / (xr[1] - xr[0] || 1)) * f.iw;
    const Y = v => pad.t + f.ih - ((v - yr[0]) / (yr[1] - yr[0] || 1)) * f.ih;
    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (i / 4) * f.ih;
      const val = (yr[1] - (i / 4) * (yr[1] - yr[0])).toFixed(0);
      grid += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y}" y2="${y}" stroke="${COL.grid}"/>
               <text x="${pad.l - 8}" y="${y + 3}" text-anchor="end" font-size="10" fill="${COL.mute}" font-family="JetBrains Mono">${val}</text>`;
    }
    let dots = data.points.map(p =>
      `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="3" fill="${FUEL_COL[p.fuel] || COL.chrome3}" fill-opacity="0.7"><title>${p.fuel} · ${p.x}L · ${p.y} L/100km</title></circle>`
    ).join('');
    let trend = '';
    if (data.trend_x && data.trend_x.length === 2) {
      trend = `<line x1="${X(data.trend_x[0])}" y1="${Y(data.trend_y[0])}" x2="${X(data.trend_x[1])}" y2="${Y(data.trend_y[1])}" stroke="${COL.accent}" stroke-width="1.6" stroke-dasharray="5 4"/>`;
    }
    // x ticks
    let xa = '';
    [0, 0.5, 1].forEach(t => {
      const x = pad.l + t * f.iw;
      xa += `<text x="${x}" y="${h - 12}" text-anchor="middle" font-size="10" fill="${COL.mute}" font-family="JetBrains Mono">${(xr[0] + t * (xr[1] - xr[0])).toFixed(1)}L</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" width="100%">${grid}${dots}${trend}${xa}</svg>`;
  }

  /* ---- line/area (cylinders) ---- */
  function line(data, { w = 520, h = 240 } = {}) {
    const pad = { l: 42, r: 18, t: 14, b: 34 };
    const f = frame(w, h, pad);
    const xs = data.labels, ys = data.values;
    const xr = [Math.min(...xs), Math.max(...xs)], yr = [0, Math.max(...ys) * 1.1];
    const X = v => pad.l + ((v - xr[0]) / (xr[1] - xr[0] || 1)) * f.iw;
    const Y = v => pad.t + f.ih - ((v - yr[0]) / (yr[1] - yr[0] || 1)) * f.ih;
    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (i / 4) * f.ih;
      const val = (yr[1] - (i / 4) * (yr[1] - yr[0])).toFixed(0);
      grid += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y}" y2="${y}" stroke="${COL.grid}"/>
               <text x="${pad.l - 8}" y="${y + 3}" text-anchor="end" font-size="10" fill="${COL.mute}" font-family="JetBrains Mono">${val}</text>`;
    }
    const pts = xs.map((x, i) => `${X(x)},${Y(ys[i])}`).join(' ');
    const area = `${pad.l},${pad.t + f.ih} ${pts} ${X(xs[xs.length - 1])},${pad.t + f.ih}`;
    let dots = xs.map((x, i) =>
      `<circle cx="${X(x)}" cy="${Y(ys[i])}" r="4" fill="${COL.chrome1}" stroke="#0a0b0f" stroke-width="1.5"><title>${x} cyl · ${ys[i]} L/100km · n=${data.counts[i]}</title></circle>`
    ).join('');
    let xa = xs.map(x => `<text x="${X(x)}" y="${h - 12}" text-anchor="middle" font-size="10" fill="${COL.mute}" font-family="JetBrains Mono">${x}</text>`).join('');
    return `<svg viewBox="0 0 ${w} ${h}" width="100%">
      <defs><linearGradient id="lg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${COL.accent}" stop-opacity="0.28"/><stop offset="1" stop-color="${COL.accent}" stop-opacity="0"/></linearGradient></defs>
      ${grid}<polygon points="${area}" fill="url(#lg)"/><polyline points="${pts}" fill="none" stroke="${COL.chrome1}" stroke-width="2"/>${dots}${xa}</svg>`;
  }

  /* ---- correlation heatmap ---- */
  function heatmap(data, { w = 520 } = {}) {
    const labels = data.labels.map(l => l.replace(' Size', '').replace(' Rating', '').replace(' Consumption', ' Cons.'));
    const n = labels.length;
    const pad = { l: 96, r: 16, t: 16, b: 80 };
    const cell = Math.min(72, (w - pad.l - pad.r) / n);
    const h = cell * n + pad.t + pad.b;
    let cells = '';
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const v = data.matrix[i][j];
        const x = pad.l + j * cell, y = pad.t + i * cell;
        // diverging chrome->accent
        const mag = Math.abs(v);
        const fill = v >= 0
          ? `rgba(143,180,217,${0.12 + mag * 0.7})`
          : `rgba(232,169,160,${0.12 + mag * 0.7})`;
        cells += `<rect x="${x}" y="${y}" width="${cell - 2}" height="${cell - 2}" rx="4" fill="${fill}"><title>${labels[i]} × ${labels[j]}: ${v}</title></rect>
                  <text x="${x + cell / 2}" y="${y + cell / 2}" text-anchor="middle" dominant-baseline="middle" font-size="11" fill="#eef1f7" font-family="JetBrains Mono">${v.toFixed(2)}</text>`;
      }
    }
    let lab = '';
    labels.forEach((l, i) => {
      lab += `<text x="${pad.l - 8}" y="${pad.t + i * cell + cell / 2}" text-anchor="end" dominant-baseline="middle" font-size="11" fill="${COL.ink}" font-family="Inter">${esc(l)}</text>`;
      const x = pad.l + i * cell + cell / 2;
      lab += `<text x="${x}" y="${pad.t + n * cell + 16}" text-anchor="end" font-size="11" fill="${COL.ink}" font-family="Inter" transform="rotate(-40 ${x} ${pad.t + n * cell + 16})">${esc(l)}</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" width="100%">${cells}${lab}</svg>`;
  }

  return { hbar, histogram, scatter, line, heatmap, FUEL_COL };
})();

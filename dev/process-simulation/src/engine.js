/* process-simulation engine: seeded discrete-event simulation of a compiled .sim plan.
   Shared by the page and its background worker, so it has no DOM access. */
var BO = (function () {
  var MONTH_START = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  function monthOf(day) {
    var d = ((day % 365) + 365) % 365, m = 11;
    while (MONTH_START[m] > d) m--;
    return m;
  }
  // 0 = Monday. The simulated calendar starts on Thursday, 1 January 2026.
  function dowOf(day) { return (3 + day) % 7; }

  function rng(seed) {
    var a = (seed >>> 0) || 1;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function windowOpen(w, hour) {
    if (!w) return true;
    return w.a <= w.b ? (hour >= w.a && hour < w.b) : (hour >= w.a || hour < w.b);
  }

  // Relative arrival intensity at minute t (0 when arrivals are closed).
  function shapeAt(arr, t) {
    var hour = (t % 1440) / 60;
    if (!windowOpen(arr.window, hour)) return 0;
    var f = 1, day = Math.floor(t / 1440);
    for (var i = 0; i < arr.peaks.length; i++) {
      var p = arr.peaks[i], hit = false;
      if (p.kind === 'month') hit = p.set.indexOf(monthOf(day)) >= 0;
      else if (p.kind === 'dow') hit = p.set.indexOf(dowOf(day)) >= 0;
      else if (p.kind === 'hour') hit = hour >= p.a && hour < p.b;
      if (hit) f *= p.f;
    }
    return f;
  }

  // The stated rate is the average while arrivals are open; peaks reshape it.
  function shapeStats(arr, horizon) {
    var s = 0, open = 0, n = 0, step = Math.max(10, horizon / 20000);
    for (var t = step / 2; t < horizon; t += step) {
      var v = shapeAt(arr, t);
      n++;
      if (v > 0) { s += v; open++; }
    }
    return { meanOpen: open ? s / open : 1, openFrac: n ? open / n : 1 };
  }

  function Heap() { this.a = []; }
  Heap.prototype.push = function (e) {
    var a = this.a; a.push(e);
    var i = a.length - 1;
    while (i > 0) {
      var p = (i - 1) >> 1;
      if (a[p].t <= e.t) break;
      a[i] = a[p]; i = p;
    }
    a[i] = e;
  };
  Heap.prototype.pop = function () {
    var a = this.a, top = a[0], last = a.pop(), n = a.length;
    if (n) {
      var i = 0;
      for (;;) {
        var l = 2 * i + 1;
        if (l >= n) break;
        var r = l + 1, m = (r < n && a[r].t < a[l].t) ? r : l;
        if (a[m].t >= last.t) break;
        a[i] = a[m]; i = m;
      }
      a[i] = last;
    }
    return top;
  };

  var RES_CAP = 20000;

  function Sim(plan, seed, opts) {
    this.p = plan;
    this.r = rng(seed);
    this.t = 0;
    this.h = new Heap();
    this.track = !!(opts && opts.track);
    this.moves = {};
    var nAttr = plan.mixN || 1, self = this;
    this.pools = plan.pools.map(function (pl) {
      return { qty: pl.qty, busy: 0, open: true, busyArea: 0, capArea: 0 };
    });
    this.steps = plan.steps.map(function () {
      return { q: [], qh: 0, qn: 0, qAttr: new Array(nAttr).fill(0), qArea: 0, wN: 0, wRes: [], done: 0, abandoned: 0 };
    });
    this.ends = new Array(plan.ends.length).fill(0);
    this.arrivals = 0;
    this.varCost = 0;
    this.inSystem = 0;
    this.finished = false;
    this.abSteps = [];
    plan.abandon.forEach(function (a, i) { if (a) self.abSteps.push(i); });
    plan.pools.forEach(function (pl, i) {
      if (pl.shift || pl.days) {
        self.pools[i].open = self.isOpen(i, 0);
        self.scheduleShift(i);
      }
    });
    this.nextArrival();
  }

  Sim.prototype.isOpen = function (i, t) {
    var pl = this.p.pools[i];
    var day = Math.floor(t / 1440), m = t - day * 1440;
    var s = pl.shift ? pl.shift.start : 0, e = pl.shift ? pl.shift.start + pl.shift.len : 1440;
    var ok = function (d) { return !pl.days || pl.days[dowOf(d)]; };
    if (ok(day) && m >= s && m < e) return true;
    if (e > 1440 && ok(day - 1) && m + 1440 < e) return true;
    return false;
  };

  Sim.prototype.scheduleShift = function (i) {
    var pl = this.p.pools[i];
    var s = pl.shift ? pl.shift.start : 0, len = pl.shift ? pl.shift.len : 1440;
    var day0 = Math.floor(this.t / 1440), best = Infinity;
    for (var d = day0 - 1; d <= day0 + 8; d++) {
      var a = d * 1440 + s, b = a + len;
      if (a > this.t + 1e-9 && a < best) best = a;
      if (b > this.t + 1e-9 && b < best) best = b;
      var midnight = d * 1440;
      if (pl.days && midnight > this.t + 1e-9 && midnight < best) best = midnight;
    }
    if (best < this.p.horizon) this.h.push({ t: best, k: 4, s: i });
  };

  Sim.prototype.sample = function (tm) {
    if (tm.k === 'f') return tm.a;
    if (tm.k === 'u') return tm.a + this.r() * (tm.b - tm.a);
    return -tm.a * Math.log(1 - this.r());
  };

  Sim.prototype.nextArrival = function () {
    var A = this.p.arrival, rmax = A.base * A.maxShape, t = this.t;
    if (!(rmax > 0)) return;
    for (var k = 0; k < 1000000; k++) {
      t += -Math.log(1 - this.r()) / rmax;
      if (t >= this.p.horizon) return;
      if (this.r() * A.maxShape < shapeAt(A, t)) { this.h.push({ t: t, k: 1 }); return; }
    }
  };

  Sim.prototype.move = function (from, to, attr, ab) {
    if (!this.track) return;
    var key = from + '>' + to + (ab ? '!' : '');
    var m = this.moves[key] || (this.moves[key] = new Array(this.p.mixN || 1).fill(0));
    m[attr]++;
  };

  Sim.prototype.targetName = function (tg) {
    return tg.e ? this.p.ends[tg.i] : this.p.steps[tg.i].name;
  };

  Sim.prototype.go = function (it, tg) {
    if (tg.e) { this.ends[tg.i]++; this.inSystem--; return; }
    var st = this.p.steps[tg.i];
    if (st.pool >= 0) {
      var S = this.steps[tg.i];
      it.inQ = true; it.qt = this.t;
      S.q.push(it); S.qn++; S.qAttr[it.a]++;
      this.tryStart(tg.i);
    } else {
      this.h.push({ t: this.t + this.sample(st.time), k: 2, s: tg.i, it: it });
    }
  };

  Sim.prototype.tryStart = function (i) {
    var S = this.steps[i], st = this.p.steps[i], pool = this.pools[st.pool];
    while (pool.open && pool.busy < pool.qty && S.qn > 0) {
      var it = S.q[S.qh++];
      it.inQ = false; S.qn--; S.qAttr[it.a]--;
      var w = this.t - it.qt;
      S.wN++;
      if (S.wRes.length < RES_CAP) S.wRes.push(w);
      else { var j = Math.floor(this.r() * S.wN); if (j < RES_CAP) S.wRes[j] = w; }
      pool.busy++;
      this.h.push({ t: this.t + this.sample(st.time), k: 2, s: i, it: it });
    }
    if (S.qh > 4096 && S.qh * 2 > S.q.length) { S.q = S.q.slice(S.qh); S.qh = 0; }
  };

  Sim.prototype.route = function (it, i) {
    var R = this.p.routes[i];
    if (R.k === 's') return R.to;
    if (R.k === 'a') return R.byAttr[it.a] || R.other;
    var u = this.r();
    for (var k = 0; k < R.cum.length; k++) if (u < R.cum[k]) return R.tos[k];
    return R.tos[R.tos.length - 1];
  };

  Sim.prototype.advance = function (t) {
    var dt = t - this.t;
    if (dt > 0) {
      for (var i = 0; i < this.pools.length; i++) {
        var o = this.pools[i];
        o.busyArea += o.busy * dt;
        if (o.open) o.capArea += o.qty * dt;
      }
      for (var j = 0; j < this.steps.length; j++) this.steps[j].qArea += this.steps[j].qn * dt;
      this.t = t;
    }
  };

  Sim.prototype.process = function (e) {
    var P = this.p;
    if (e.k === 1) {
      var a = 0;
      if (P.mixN > 1) { var u = this.r(); while (a < P.mixN - 1 && u >= P.mixCum[a]) a++; }
      var it = { a: a, inQ: false, qt: 0 };
      this.arrivals++; this.inSystem++;
      this.move('src', this.targetName(P.entry), a);
      this.go(it, P.entry);
      this.nextArrival();
    } else if (e.k === 2) {
      var st = P.steps[e.s], S = this.steps[e.s];
      S.done++;
      this.varCost += st.cost;
      if (st.pool >= 0) this.pools[st.pool].busy--;
      var tg = this.route(e.it, e.s);
      this.move(st.name, this.targetName(tg), e.it.a);
      this.go(e.it, tg);
      if (st.pool >= 0) {
        var ps = P.poolSteps[st.pool];
        for (var k = 0; k < ps.length; k++) this.tryStart(ps[k]);
      }
    } else if (e.k === 4) {
      var o = this.pools[e.s];
      o.open = this.isOpen(e.s, this.t + 1e-6);
      if (o.open) {
        var ps2 = P.poolSteps[e.s];
        for (var k2 = 0; k2 < ps2.length; k2++) this.tryStart(ps2[k2]);
      }
      this.scheduleShift(e.s);
    }
  };

  // Earliest abandonment among queues with patience: the head of each FIFO queue leaves first.
  Sim.prototype.nextAbandon = function () {
    var best = Infinity, bi = -1, ab = this.abSteps;
    for (var k = 0; k < ab.length; k++) {
      var i = ab[k], S = this.steps[i];
      if (S.qn > 0) {
        var d = S.q[S.qh].qt + this.p.abandon[i].after;
        if (d < best) { best = d; bi = i; }
      }
    }
    this.abI = bi;
    return best;
  };

  Sim.prototype.abandonHead = function (i) {
    var S = this.steps[i], it = S.q[S.qh++], ab = this.p.abandon[i];
    it.inQ = false; S.qn--; S.qAttr[it.a]--; S.abandoned++;
    this.move(this.p.steps[i].name, this.p.ends[ab.to.i], it.a, true);
    this.ends[ab.to.i]++; this.inSystem--;
  };

  Sim.prototype.runUntil = function (T) {
    if (T > this.p.horizon) T = this.p.horizon;
    var h = this.h.a;
    for (;;) {
      var tE = h.length ? h[0].t : Infinity, tA = this.abSteps.length ? this.nextAbandon() : Infinity;
      if (tA <= tE) {
        if (tA > T) break;
        this.advance(tA);
        this.abandonHead(this.abI);
      } else {
        if (tE > T) break;
        var e = this.h.pop();
        this.advance(e.t);
        this.process(e);
      }
    }
    this.advance(T);
    if (T >= this.p.horizon) this.finished = true;
  };

  Sim.prototype.takeMoves = function () { var m = this.moves; this.moves = {}; return m; };

  function quant(sorted, p) {
    var n = sorted.length;
    if (!n) return 0;
    var x = p * (n - 1), i = Math.floor(x), f = x - i;
    return i + 1 < n ? sorted[i] * (1 - f) + sorted[i + 1] * f : sorted[i];
  }

  Sim.prototype.results = function () {
    var P = this.p, el = Math.max(this.t, 1e-9), self = this;
    var res = { elapsed: el, arrivals: this.arrivals, ends: {}, waitSorted: {}, queueAvg: {}, queueNow: {}, util: {}, busy: {}, cost: 0 };
    P.ends.forEach(function (n, i) { res.ends[n] = self.ends[i]; });
    P.steps.forEach(function (st, i) {
      var S = self.steps[i];
      res.waitSorted[st.name] = S.wRes.slice().sort(function (a, b) { return a - b; });
      res.queueAvg[st.name] = S.qArea / el;
      res.queueNow[st.name] = S.qn;
    });
    var fixed = 0;
    P.pools.forEach(function (pl, i) {
      var o = self.pools[i];
      res.util[pl.name] = o.capArea > 0 ? o.busyArea / o.capArea : 0;
      res.busy[pl.name] = o.busy;
      fixed += pl.qty * pl.costPerMin * el;
    });
    res.cost = this.varCost + fixed;
    return res;
  };

  function metric(m, res) {
    if (m.kind === 'count') return res.ends[m.x] || 0;
    if (m.kind === 'share') {
      var tot = 0;
      for (var k in res.ends) tot += res.ends[k];
      return tot ? (res.ends[m.x] || 0) / tot : 0;
    }
    if (m.kind === 'wait') return quant(res.waitSorted[m.x] || [], m.p);
    if (m.kind === 'queue') return res.queueAvg[m.x] || 0;
    if (m.kind === 'util') return res.util[m.x] || 0;
    if (m.kind === 'cost') return res.cost / res.elapsed * m.per;
    return 0;
  }

  return { Sim: Sim, metric: metric, quant: quant, shapeAt: shapeAt, shapeStats: shapeStats, monthOf: monthOf, dowOf: dowOf };
})();

/* Worker side: runs many seeds for the range and the scenario comparison. */
if (typeof window === 'undefined' && typeof self !== 'undefined' && typeof importScripts === 'function') {
  self.onmessage = function (ev) {
    var d = ev.data, out = [], done = 0, total = d.configs.length * d.seeds.length;
    d.configs.forEach(function (c) {
      var vals = d.shows.map(function () { return []; });
      d.seeds.forEach(function (s) {
        var sim = new BO.Sim(c.plan, s, {});
        sim.runUntil(c.plan.horizon);
        var res = sim.results();
        d.shows.forEach(function (m, k) { vals[k].push(BO.metric(m, res)); });
        done++;
        self.postMessage({ type: 'progress', id: d.id, done: done, total: total });
      });
      out.push({ key: c.key, vals: vals });
    });
    self.postMessage({ type: 'done', id: d.id, out: out });
  };
}

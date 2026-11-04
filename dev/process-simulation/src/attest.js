// The simulation as an OKF Attested Computation: a run gives a receipt (the recipe's sha256, the engine, the seed, the
// runs, the controls set and the numbers), and the attester checks a receipt against the recipe by running it again —
// no model, no network, no dependency. Appended to the engine (BO, SIMLANG in scope) for scripts/engine.mjs, the
// mod's sim-core.js and the attester an OKF bundle carries.
var ATTEST = (function () {
  // SHA-256 (FIPS 180-4) over the UTF-8 bytes of a string, in plain JS so it runs where node:crypto does not (the mod)
  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
    0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
    0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]
  function sha256(text) {
    var bytes = new TextEncoder().encode(text)
    var len = bytes.length
    var padded = new Uint8Array(((len + 9 + 63) >> 6) << 6)
    padded.set(bytes)
    padded[len] = 0x80
    var bits = len * 8
    var view = new DataView(padded.buffer)
    view.setUint32(padded.length - 8, Math.floor(bits / 0x100000000))
    view.setUint32(padded.length - 4, bits >>> 0)
    var h = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]
    var w = new Array(64)
    var rot = function (x, n) { return (x >>> n) | (x << (32 - n)) }
    for (var off = 0; off < padded.length; off += 64) {
      for (var i = 0; i < 16; i++) w[i] = view.getUint32(off + i * 4)
      for (i = 16; i < 64; i++) {
        var s0 = rot(w[i - 15], 7) ^ rot(w[i - 15], 18) ^ (w[i - 15] >>> 3)
        var s1 = rot(w[i - 2], 17) ^ rot(w[i - 2], 19) ^ (w[i - 2] >>> 10)
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0
      }
      var a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], k = h[7]
      for (i = 0; i < 64; i++) {
        var t1 = (k + (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0
        var t2 = ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0
        k = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
      }
      h = [(h[0] + a) | 0, (h[1] + b) | 0, (h[2] + c) | 0, (h[3] + d) | 0, (h[4] + e) | 0, (h[5] + f) | 0, (h[6] + g) | 0, (h[7] + k) | 0]
    }
    return h.map(function (x) { return (x >>> 0).toString(16).padStart(8, '0') }).join('')
  }

  var metricName = function (m) { return m.kind + (m.pn ? ' p' + m.pn : '') + (m.x ? ' ' + m.x : m.perName ? ' per ' + m.perName : '') }
  var knobText = function (knob, v) { return knob.pct ? Math.round(v * 100) + '%' : String(v) }

  /** Runs a recipe over its seeded runs: { ok, diags, model, knobs, receipt }. `engine` names the engine in the receipt. */
  function run(src, opts) {
    opts = opts || {}
    var set = opts.set || {}
    var r = SIMLANG.parse(src)
    if (!r.ok) return { ok: false, diags: r.diags }
    var knobs = {}
    r.model.knobOrder.forEach(function (k) { knobs[k] = k in set ? set[k] : r.model.knobs[k].init })
    var plan = SIMLANG.compile(r.model, knobs)
    var expected = plan.statedPerMin * plan.openFrac * plan.horizon
    var n = Math.max(1, Number(opts.seeds != null ? opts.seeds : expected > 200000 ? 6 : 10))
    var values = r.model.shows.map(function () { return [] })
    for (var i = 0; i < n; i++) {
      var sim = new BO.Sim(plan, r.model.seed * 1009 + i * 7919 + 1, {})
      sim.runUntil(plan.horizon)
      var res = sim.results()
      r.model.shows.forEach(function (m, j) { values[j].push(BO.metric(m, res)) })
    }
    var rows = r.model.shows.map(function (m, j) {
      var v = values[j].sort(function (a, b) { return a - b })
      return { metric: metricName(m), p10: BO.quant(v, 0.1), median: BO.quant(v, 0.5), p90: BO.quant(v, 0.9) }
    })
    var used = {}
    Object.keys(set).forEach(function (k) { if (k in r.model.knobs) used[k] = set[k] })
    return {
      ok: true, diags: r.diags, model: r.model, knobs: knobs,
      receipt: { format: 'dna/process-simulation/receipt-v1', recipe_sha256: sha256(src), engine: opts.engine || 'dna/process-simulation', seed: r.model.seed, runs: n, set: used, rows: rows },
    }
  }

  var close = function (a, b) { return a === b || Math.abs(a - b) <= 1e-9 * Math.max(Math.abs(a), Math.abs(b)) }
  var minor = function (engine) { var m = /(\d+)\.(\d+)\.\d+/.exec(String(engine || '')); return m ? m[1] + '.' + m[2] : '' }

  /** Checks a receipt against the recipe, in order, stopping at the first that fails: { ok, reason?, checked }. */
  function attest(receipt, src, engine) {
    var checked = []
    var no = function (reason) { return { ok: false, reason: reason, checked: checked } }
    if (!receipt || receipt.format !== 'dna/process-simulation/receipt-v1') return no('not a receipt of dna/process-simulation')
    if (receipt.recipe_sha256 !== sha256(src)) return no('the recipe was swapped')
    checked.push('recipe')
    var p = SIMLANG.parse(src)
    if (!p.ok) return no('the recipe has errors')
    var set = receipt.set || {}
    for (var k in set) {
      var knob = p.model.knobs[k]
      if (!knob) return no(k + ' is not a parameter')
      if (!(set[k] >= knob.min && set[k] <= knob.max)) return no(k + '=' + knobText(knob, set[k]) + ' is outside ' + knobText(knob, knob.min) + '..' + knobText(knob, knob.max))
    }
    checked.push('parameters')
    var version = /\/(\d+\.\d+\.\d+)$/.exec(String(receipt.engine || ''))
    if (minor(receipt.engine) !== minor(engine)) return no('made by another engine (' + (version ? version[1] : receipt.engine) + ')')
    checked.push('engine')
    var again = run(src, { seeds: receipt.runs, set: set, engine: engine }).receipt
    var rows = receipt.rows || []
    if (rows.length !== again.rows.length) return no('the receipt has ' + rows.length + ' metrics, the recipe ' + again.rows.length)
    for (var i = 0; i < rows.length; i++) {
      var a = rows[i], b = again.rows[i]
      if (a.metric !== b.metric) return no('metric ' + (i + 1) + ' is «' + a.metric + '» in the receipt, «' + b.metric + '» in the recipe')
      var keys = ['p10', 'median', 'p90']
      for (var j = 0; j < keys.length; j++) {
        if (!close(a[keys[j]], b[keys[j]])) return no(a.metric + ': the receipt says ' + a[keys[j]] + ' (' + keys[j] + '), run again it is ' + b[keys[j]])
      }
    }
    checked.push('numbers')
    return { ok: true, checked: checked }
  }

  return { sha256: sha256, run: run, attest: attest, metricName: metricName }
})()

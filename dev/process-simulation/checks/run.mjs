// Regression tests: examples parse cleanly, translation round-trips, locales agree,
// seeded results match the snapshot, and broken recipes get the expected validator message.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
// what the skill ships: its engine and its examples
import { BO, SIMLANG } from '../../../skills/process-simulation/scripts/engine.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(here, '../../../skills/process-simulation/examples');
function initialKnobs(model, overrides = {}) {
  const k = {};
  for (const name of model.knobOrder) k[name] = name in overrides ? overrides[name] : model.knobs[name].init;
  return k;
}
function runSeeds(model, knobs, seeds) {
  const plan = SIMLANG.compile(model, knobs);
  const values = model.shows.map(() => []);
  for (const s of seeds) {
    const sim = new BO.Sim(plan, s, {});
    sim.runUntil(plan.horizon);
    const res = sim.results();
    model.shows.forEach((m, i) => values[i].push(BO.metric(m, res)));
  }
  return values.map(v => v.sort((a, b) => a - b));
}

const update = process.argv.includes('--update');
const newSnaps = [];
const snapPath = join(here, 'snapshots.json');
const snaps = existsSync(snapPath) ? JSON.parse(readFileSync(snapPath, 'utf8')) : {};
let failed = 0, passed = 0;
const check = (name, ok, detail = '') => {
  if (ok) passed++; else { failed++; console.log(`FAIL ${name} ${detail}`); }
};
const round = v => Math.round(v * 1e6) / 1e6;

const index = JSON.parse(readFileSync(join(EXAMPLES, 'index.json'), 'utf8'));
for (const ex of index) {
  const src = readFileSync(join(EXAMPLES, ex.file), 'utf8');
  const r = SIMLANG.parse(src);
  check(`${ex.file} parses without errors`, r.ok, JSON.stringify(r.diags.map(d => d.text)));
  if (!r.ok) continue;

  const lang = r.model.lang, other = lang === 'en' ? 'pt-BR' : 'en';
  const there = SIMLANG.translate(src, other), back = SIMLANG.translate(there, lang);
  check(`${ex.file} translation round-trips exactly`, back === src);

  const r2 = SIMLANG.parse(there);
  check(`${ex.file} translated recipe parses`, r2.ok, JSON.stringify(r2.diags.map(d => d.text)));

  const seeds = [1];
  const a = runSeeds(r.model, initialKnobs(r.model), seeds).map(v => round(v[0]));
  if (r2.ok) {
    const b = runSeeds(r2.model, initialKnobs(r2.model), seeds).map(v => round(v[0]));
    check(`${ex.file} same numbers in ${lang} and ${other}`, JSON.stringify(a) === JSON.stringify(b), `${a} vs ${b}`);
  }
  if (update || !snaps[ex.file]) { snaps[ex.file] = a; newSnaps.push(ex.file); }
  else check(`${ex.file} matches snapshot`, JSON.stringify(snaps[ex.file]) === JSON.stringify(a), `${snaps[ex.file]} vs ${a}`);
}

// Validator: each broken recipe must produce the named message.
const base = 'sim "t"\nhorizon 1 day\narrive item 10/hour\nstep a time 1min\nend done\n';
const cases = [
  ['branch sum', base + 'end other\na ->\n  done 60%\n  other 30%\nshow count end done', 'sum'],
  ['undeclared knob', base + 'a -> done\nshow count end done\nknob x 1..2 = 1\npool p $y', 'knobUndefined'],
  ['unknown target', base + 'a -> nowhere\nshow count end done', 'unknownTarget'],
  ['missing route', base + 'show count end done', 'noRoute'],
  ['bad duration', base.replace('1min', '1 parsec') + 'a -> done', 'badDur'],
  ['mixed locale', base + 'a -> done\netapa b tempo 1min\nb -> done', 'locale'],
  ['loop with no way out', base + 'step b time 1min\na -> b\nb -> a', 'noExit'],
  ['knob without rest', base + 'end other\nknob r 0%..50% = 10%\na ->\n  done $r\n  other 90%', 'knobNeedsRest']
];
for (const [name, src, key] of cases) {
  const r = SIMLANG.parse(src);
  check(`validator: ${name} -> ${key}`, r.diags.some(d => d.key === key), JSON.stringify(r.diags.map(d => d.key)));
}

// Rework: a review that sends a fifth back. Accepted; every visit counts in the flow (10/hour in, 12.5/hour through
// the work: 10 / (1 - 20%)); the return is the one back edge; every item still finishes; a way out with no share warns.
{
  const src = 'sim "rework"\nhorizon 30 day\nseed 3\narrive item 10/hour\npool people 4\nstep work by people time ~10min\nstep review time 2min\nend done\nknob back 0%..100% = 20%\nwork -> review\nreview ->\n  work $back\n  done rest\nshow count end done\nshow utilization people\n';
  const r = SIMLANG.parse(src);
  check('a loop with a way out is a valid recipe', r.ok, JSON.stringify(r.diags.map(d => d.text)));
  const plan = SIMLANG.compile(r.model, initialKnobs(r.model)), fl = SIMLANG.flows(r.model, plan);
  check('a loop counts every visit in the flow', Math.abs(fl.inflow[0] * 60 - 12.5) < 1e-6 && Math.abs(fl.inflow[1] * 60 - 12.5) < 1e-6, String(fl.inflow.map(v => v * 60)));
  check('the return is the back edge', JSON.stringify(plan.back) === '[[],[0]]', JSON.stringify(plan.back));
  const done = runSeeds(r.model, initialKnobs(r.model), [3])[0][0];
  check('every item of a loop still finishes', done > 7000 && done < 7400, String(done));
  const stuck = SIMLANG.flows(r.model, SIMLANG.compile(r.model, { back: 1 }));
  check('a loop whose way out has no share is named', stuck.endless.includes('work') && stuck.endless.includes('review'), JSON.stringify(stuck.endless));
}

// Determinism: same seed, same result.
{
  const src = readFileSync(join(EXAMPLES, 'hr-help-desk.sim'), 'utf8'), r = SIMLANG.parse(src);
  const x = runSeeds(r.model, initialKnobs(r.model), [42]), y = runSeeds(r.model, initialKnobs(r.model), [42]);
  check('same seed gives the same run', JSON.stringify(x) === JSON.stringify(y));
}

if (update) writeFileSync(snapPath, JSON.stringify(snaps, null, 2) + '\n');
console.log(`${passed} passed, ${failed} failed${update ? ' (snapshots updated)' : ''}`);
process.exit(failed ? 1 : 0);

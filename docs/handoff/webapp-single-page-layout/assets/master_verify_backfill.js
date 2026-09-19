/* Master (independent) probe for the P0-3 backfill rule.
 *
 * Loads the real ``backfillPlan`` + the two maps out of webapp/static/app.js
 * (no copy of the logic lives here) and asserts the contract from
 * docs/handoff/webapp-single-page-layout/task.md section 1.3 / 1.4.
 *
 * Usage:  node docs/handoff/webapp-single-page-layout/assets/master_verify_backfill.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const APP_JS = path.join(ROOT, 'webapp', 'static', 'app.js');
const source = fs.readFileSync(APP_JS, 'utf8');

function grab(re) {
  const m = source.match(re);
  if (!m) {
    throw new Error('pattern not found in app.js: ' + re);
  }
  return m[0];
}

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(
  grab(/const OUTPUT_FIELD_MAP = \{[\s\S]*?\n\};/) + '\n' +
  grab(/const DRAWER_FIELD_MAP = \{[\s\S]*?\n\};/) + '\n' +
  grab(/function cleanText\([\s\S]*?\n\}\n/) + '\n' +
  grab(/function backfillPlan\([\s\S]*?\n\}\n/) + '\n' +
  'this.plan = backfillPlan;',
  sandbox
);
const plan = sandbox.plan;

let failures = 0;
function check(name, condition, detail) {
  const ok = !!condition;
  if (!ok) {
    failures += 1;
  }
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '  <-- ' + detail));
}

function run(outputs, values, drawer, options) {
  return plan(outputs, values || {}, drawer || {}, options || {});
}

/* 1. every documented mapping from task 1.4 is honoured */
const mapping = [
  ['genome_fasta', 'genome_fasta'],
  ['target_fasta', 'search_fasta'],
  ['mask_fasta', 'mask_fasta'],
  ['output_dir', 'output_dir'],
  ['blastdb', 'blastdb'],
  ['index_path', 'index_path'],
  ['search_fasta', 'search_fasta'],
  ['bed_regions', 'bed_regions'],
];
for (const pair of mapping) {
  const key = pair[0];
  const field = pair[1];
  const out = {};
  out[key] = 'X:/p/' + key;
  const res = run(out, {}, {});
  check('mapping ' + key + ' -> ' + field,
        res.updates[field] === 'X:/p/' + key,
        JSON.stringify(res));
}

/* 2. ``annotation`` is drawer-only: never written into the main area */
{
  const res = run({annotation: 'X:/p/a.gff3'}, {}, {});
  check('annotation goes to the drawer only',
        !Object.keys(res.updates).length
        && res.drawerUpdates['dp-annotation'] === 'X:/p/a.gff3',
        JSON.stringify(res));
}

/* 3. user-typed main value wins */
{
  const res = run({output_dir: 'NEW'}, {output_dir: 'TYPED'}, {});
  check('typed main value is never overwritten',
        res.updates.output_dir === undefined && res.skipped.indexOf('output_dir') >= 0,
        JSON.stringify(res));
}

/* 4. user-typed *drawer* value wins for a key that exists in both places
      (this is the union rule the servant added after the probe caught it) */
{
  const res = run({genome_fasta: 'NEW'}, {}, {'dp-genome': 'TYPED'});
  check('typed drawer value blocks the main-area write',
        res.updates.genome_fasta === undefined && res.skipped.indexOf('genome_fasta') >= 0,
        JSON.stringify(res));
}

/* 5. skip_mask leaves mask_fasta alone but still fills the rest */
{
  const res = run({mask_fasta: 'M', target_fasta: 'T'}, {}, {}, {skipMask: true});
  check('skip_mask keeps mask_fasta untouched',
        res.updates.mask_fasta === undefined,
        JSON.stringify(res));
  check('skip_mask still fills other keys',
        res.updates.search_fasta === 'T',
        JSON.stringify(res));
}

/* 6. blank / whitespace values are skipped, unknown keys are reported */
{
  const res = run({target_fasta: '   ', mystery: 'Z:/x'}, {}, {});
  check('blank value is skipped', !Object.keys(res.updates).length, JSON.stringify(res));
  check('unknown key is reported as ignored',
        res.ignored.indexOf('mystery') >= 0, JSON.stringify(res));
}

/* 7. a fully-empty field set fills everything */
{
  const res = run(
    {genome_fasta: 'G', target_fasta: 'T', mask_fasta: 'M', output_dir: 'O', blastdb: 'B'},
    {}, {}
  );
  check('all five empty fields are filled at once',
        Object.keys(res.updates).length === 5
        && Object.keys(res.skipped).length === 0
        && res.updates.search_fasta === 'T'
        && res.updates.genome_fasta === 'G'
        && res.updates.mask_fasta === 'M'
        && res.updates.output_dir === 'O'
        && res.updates.blastdb === 'B',
        JSON.stringify(res));
}

console.log('');
console.log('master_verify_backfill.js: ' + (failures ? failures + ' FAILURE(S)' : 'all checks passed'));
process.exit(failures ? 1 : 0);

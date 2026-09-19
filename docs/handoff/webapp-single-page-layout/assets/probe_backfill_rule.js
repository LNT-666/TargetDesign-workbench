#!/usr/bin/env node
/*
 * Rule-level probe for task P0-3 (webapp-single-page-layout).
 *
 * The back-fill decision lives in the browser (webapp/static/app.js), so this
 * probe extracts the real ``backfillPlan()`` source out of that file and runs
 * it against the table in task.md section 1.3. Nothing is re-implemented here:
 * if the shipped rule changes, these cases fail.
 *
 *   node docs/handoff/webapp-single-page-layout/assets/probe_backfill_rule.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', '..', '..', '..');
const appPath = path.join(root, 'webapp', 'static', 'app.js');
const source = fs.readFileSync(appPath, 'utf8');

function extractFunction(text, name) {
  const start = text.indexOf('function ' + name + '(');
  if (start < 0) {
    throw new Error('function ' + name + '() not found in app.js');
  }
  let depth = 0;
  let index = text.indexOf('{', start);
  for (let i = index; i < text.length; i += 1) {
    if (text[i] === '{') {
      depth += 1;
    } else if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        return text.slice(start, i + 1);
      }
    }
  }
  throw new Error('unbalanced braces while extracting ' + name + '()');
}

function extractConstObject(text, name) {
  const start = text.indexOf('const ' + name + ' = {');
  if (start < 0) {
    throw new Error('const ' + name + ' not found in app.js');
  }
  const end = text.indexOf('\n};', start);
  if (end < 0) {
    throw new Error('unterminated const ' + name);
  }
  return text.slice(start, end + 3);
}

const harness = [
  extractConstObject(source, 'OUTPUT_FIELD_MAP'),
  extractConstObject(source, 'DRAWER_FIELD_MAP'),
  extractFunction(source, 'cleanText'),
  extractFunction(source, 'backfillPlan'),
  'module.exports = {backfillPlan: backfillPlan, OUTPUT_FIELD_MAP: OUTPUT_FIELD_MAP,'
    + ' DRAWER_FIELD_MAP: DRAWER_FIELD_MAP};',
].join('\n\n');

const sandbox = {module: {exports: {}}, exports: {}};
vm.runInNewContext(harness, sandbox, {filename: 'app.js#backfillPlan'});
const backfillPlan = sandbox.module.exports.backfillPlan;

let failures = 0;
function check(label, cond, detail) {
  if (cond) {
    console.log('PASS ' + label);
  } else {
    failures += 1;
    console.log('FAIL ' + label + (detail ? ('  -> ' + detail) : ''));
  }
}

const outputs = {
  genome_fasta: 'R:\\g\\genome.fa',
  annotation: 'R:\\g\\ann.gtf',
  target_fasta: 'R:\\g\\GENE1-gene.fa',
  mask_fasta: 'R:\\g\\GENE2-gene.fa',
  output_dir: 'R:\\g\\out',
  blastdb: 'R:\\g\\out\\blastdb',
  index_path: 'R:\\g\\idx\\genome',
};

/* 1.3 mapping table: every key lands in the expected main-area field. */
const plan = backfillPlan(outputs, {}, {}, {});
check('target_fasta -> search_fasta',
  plan.updates.search_fasta === outputs.target_fasta);
check('genome_fasta -> genome_fasta',
  plan.updates.genome_fasta === outputs.genome_fasta);
check('mask_fasta -> mask_fasta',
  plan.updates.mask_fasta === outputs.mask_fasta);
check('output_dir -> output_dir',
  plan.updates.output_dir === outputs.output_dir);
check('blastdb -> blastdb', plan.updates.blastdb === outputs.blastdb);
check('index_path -> index_path', plan.updates.index_path === outputs.index_path);
check('annotation stays out of the main area (recorded in the drawer only)',
  plan.drawerUpdates['dp-annotation'] === outputs.annotation
    && plan.updates.annotation === undefined);
check('nothing ignored for the documented keys', plan.ignored.length === 0,
  JSON.stringify(plan.ignored));

/* Only empty fields are filled; typed values win. */
const filled = backfillPlan(outputs,
  {search_fasta: '', output_dir: 'R:\\typed\\by\\user'}, {}, {});
check('empty field is filled', filled.updates.search_fasta === outputs.target_fasta);
check('user value is never overwritten', filled.updates.output_dir === undefined);
check('overwritten field is reported as skipped',
  filled.skipped.indexOf('output_dir') >= 0, JSON.stringify(filled.skipped));

/* skip_mask keeps mask_fasta untouched. */
const skippedMask = backfillPlan(
  {mask_fasta: outputs.mask_fasta, target_fasta: outputs.target_fasta},
  {}, {}, {skipMask: true});
check('skip_mask leaves mask_fasta alone', skippedMask.updates.mask_fasta === undefined);
check('skip_mask still fills the other keys',
  skippedMask.updates.search_fasta === outputs.target_fasta);

/* Empty values and unknown keys are ignored, not written. */
const noisy = backfillPlan({target_fasta: '   ', genome_fasta: null, nope: 'R:\\x'},
  {}, {}, {});
check('blank value is skipped', Object.keys(noisy.updates).length === 0);
check('unknown key is recorded as ignored', noisy.ignored.indexOf('nope') >= 0);

/* A drawer value the user already typed is not overwritten either. */
const drawerKept = backfillPlan({genome_fasta: outputs.genome_fasta},
  {}, {'dp-genome': 'R:\\typed\\genome.fa'}, {});
check('typed drawer value is kept',
  drawerKept.drawerUpdates['dp-genome'] === undefined
    && drawerKept.skipped.indexOf('genome_fasta') >= 0);

console.log('');
console.log(failures === 0
  ? 'probe_backfill_rule.js: all checks passed'
  : 'probe_backfill_rule.js: ' + failures + ' check(s) FAILED');
process.exit(failures === 0 ? 0 : 1);
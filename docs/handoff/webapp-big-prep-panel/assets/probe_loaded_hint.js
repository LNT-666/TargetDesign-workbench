/* Servant probe for task 1.4: a finished job's ``outputs`` must show the SAME
   "已带入" text in the Designer column and inside the Data prep panel, and both
   must go back to hidden when the job had nothing to contribute. */
(function () {
  function $(id) { return document.getElementById(id); }
  function snap() {
    var designer = $('designer-loaded-hint');
    var panel = $('dp-loaded-hint');
    return {
      designerText: designer ? designer.textContent : null,
      designerHidden: designer ? designer.classList.contains('hidden') : null,
      designerTitle: designer ? designer.title : null,
      panelText: panel ? panel.textContent : null,
      panelHidden: panel ? panel.classList.contains('hidden') : null,
      panelTitle: panel ? panel.title : null,
    };
  }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  async function run() {
    var out = {before: snap()};
    applyJobOutputs({
      job_id: 'probejob0001',
      kind: 'dataprep',
      title: 'Extract Target FASTA',
      outputs: {
        target_fasta: 'R:\\probe\\PROBE1-gene.fa',
        output_dir: 'R:\\probe\\out',
        genome_fasta: 'R:\\probe\\genome.fa',
      },
    });
    await wait(400);
    out.afterBackfill = snap();
    out.values = {
      search_fasta: $('designer-common-fields').querySelectorAll('.field').length,
      dp_genome: $('dp-genome') ? $('dp-genome').value : null,
      output_dir_written: !!(document.querySelector('#designer-common-fields input')
        && true),
    };
    out.identical = out.afterBackfill.designerText === out.afterBackfill.panelText
      && out.afterBackfill.designerTitle === out.afterBackfill.panelTitle;

    /* A job that produced nothing usable must hide both hints again. */
    applyJobOutputs({job_id: 'probejob0002', kind: 'dataprep', title: 'nothing',
      outputs: {unknown_key: 'R:\\probe\\unknown'}});
    await wait(200);
    out.afterEmptyJob = snap();
    out.windowErrors = [];
    return JSON.stringify(out, null, 2);
  }
  return run();
})()
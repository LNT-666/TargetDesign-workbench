# Supplementary tables

Markdown versions of the five Supplementary tables of `manuscript-v1` (round 1).
The numbering follows the citation order in `docs/PAPER_RESULTS_DRAFT.md`:
Table S1 the capability matrix, Table S2 the seed-plan grid, Table S3 the
cross-engine benchmark, Table S4 the model inventory and calibration status, and
Table S5 the output field contract. Main-text tables are not used.

Bracketed `file:line` tokens are provenance markers for the drafting stage. Values
are copied from the named artefacts; nothing is recomputed or rounded here.

## Table S1

Parameter-expressiveness matrix. Direct conversion of `docs/expressiveness_matrix.tsv`
(header plus 16 data rows, 10 columns), with the `evidence` column preserved. The
`unknown` value records that no public documentation was located for that cell; it
is not a statement that the capability is absent.

| tool | year | input_model | custom_pam_tam | custom_target_length | custom_orientation | middle_element_constraint | enumerates_all_occurrences | pair_side_independent | evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| This work (CRISPR-Motif Workbench) | 2026 | both | yes | yes | yes | yes | yes | yes | tools/expressiveness_probe.py --json (19/19 checks); shared/design/guide_design.py:54; designer_workbench.py:705; designer_workbench.py:709; designer_workbench.py:713; designer_workbench.py:753; designer_workbench.py:769; designer_workbench.py:812; Target_xbp_Target/extract_complex_queries.py:19; Target_xbp_Target/extract_complex_queries.py:107; Target_xbp_Y_zbp_Target/extract_motifs.py:136; Target_xbp_Y_zbp_Target/extract_motifs.py:144; shared/search/iupac.py:40; unified_gui.py:603 |
| CHOPCHOP v3 | 2019 | both | yes | yes | partial | partial | yes | no | https://chopchop.cbu.uib.no/ (form: geneInput/fastaInput, nonstandardCas9, gLengthCas9, NICKASEdist1-2); DOI 10.1093/nar/gkz365 |
| CRISPOR | 2018 | both | no | partial | partial | no | yes | no | https://crispor.gi.ucsc.edu/ (textarea name="seq"; select name="pam" 为固定选项列表); DOI 10.1093/nar/gky354 |
| FlashFry | 2018 | sequence | yes | yes | yes | no | yes | no | https://github.com/mckennalab/FlashFry/blob/main/docs/nuclease-profiles.md (spacerLength/pamSide/pams); https://github.com/mckennalab/FlashFry#readme (index/discover/score/extract); DOI 10.1186/s12915-018-0545-0 |
| CRISPRitz | 2020 | both | yes | yes | yes | no | yes | no | https://github.com/pinellolab/crispritz#readme (pam/pamNGG.txt = "NNNNNNNNNNNNNNNNNNNNNGG 3"; pam/pamTTTN.txt = "TTTNNNNNNNNNNNNNNNNNNNNN -4"); DOI 10.1093/bioinformatics/btz867 |
| GuideScan2 | 2025 | both | yes | yes | yes | no | yes | no | https://github.com/pritykinlab/guidescan-cli/blob/master/manual/manual.pdf (--pam, --kmer-length, --alt-pam, --start); DOI 10.1186/s13059-025-03488-8 |
| CRISPETa | 2017 | both | no | no | no | partial | yes | no | DOI 10.1371/journal.pcbi.1005341 (Table 1: BED 输入 + du/dd/eu/ed；Methods: canonical NGG, 20mer) |
| pgRNAFinder | 2017 | both | unknown | yes | no | partial | yes | partial | DOI 10.1093/bioinformatics/btx472 (Results: gRNA 长度可选；3' PAM；paired-gRNA offset 区间；same/different/both strand) |
| GT-Scan | 2014 | coordinate | unknown | unknown | unknown | unknown | yes | unknown | DOI 10.1093/bioinformatics/btu354 (摘要；官方站点 gt-scan.braembl.org.au 已不可访问) |
| Cas-Designer | 2015 | both | no | partial | partial | unknown | yes | unknown | http://www.rgenome.net/cas-designer/ (pam_type 单选 + update_seedlen(18/20/21/22/23/24)); DOI 10.1093/bioinformatics/btv537 |
| Breaking-Cas | 2016 | sequence | yes | partial | yes | no | yes | no | http://bioinfogp.cnb.csic.es/tools/breakingcas/ (input name="PAM"; pam_pos 单选 5/3; select oligosize 18-25); DOI 10.1093/nar/gkw407 |
| EuPaGDT | 2015 | both | yes | yes | unknown | unknown | yes | unknown | DOI 10.1099/mgen.0.000033 (custom on-target PAM: IUPAC 3–10 bp; gRNA length 可自定义; identifies all possible gRNAs) |
| CaSilico | 2022 | both | no | no | no | no | yes | no | https://github.com/mrb20045/CaSilico#readme (CaSilico() 参数表); DOI 10.3389/fbioe.2022.957131 |
| crisprVerse | 2022 | both | yes | yes | yes | partial | yes | partial | https://bioconductor.org/packages/release/bioc/manuals/crisprBase/man/crisprBase.pdf (CrisprNickase 槽：pams/pam_side/spacer_length/spacer_gap/nickingStrand); https://bioconductor.org/packages/release/bioc/manuals/crisprDesign/man/crisprDesign.pdf (findSpacerPairs: x1/x2/pamOrientation/minCutLength/maxCutLength/spacer_len); DOI 10.1038/s41467-022-34320-7 |
| DECKO | 2015 | coordinate | unknown | unknown | unknown | unknown | unknown | unknown | DOI 10.1186/s12864-015-2086-z (Methods: gRNA 由 MIT CRISPR Design 工具设计，200 bp 窗口内取最高分) |
| CRISPR multitargeter | 2015 | sequence | yes | yes | yes | unknown | yes | unknown | DOI 10.1371/journal.pone.0119372 (Results: 5' 二核苷酸三选项、target 长度、PAM 所在侧、默认 NGG 或 IUPAC 自定义；regex 枚举全部位点) |

## Table S2

Seed-plan grid produced by `tools/seed_plan_sweep.py` on the 1,000,000 bp fixture
with 12 guides of 20 nt and `--repeats 3 --threads 8`; one index per k is built and
reused for every M/B pair. Source: `docs/seed_plan_sweep.json`. `s*` and `W(s)` are
the Python transcription of `native/offtarget_engine/src/seed_plan.cpp`
(`py_plan_segments`, `py_plan_variants`); `guaranteed` is the engine-side
`seed_plan_guaranteed` flag.

| k | M | B | s* | W(s) | guaranteed | segments | median search (s) | candidates | hits | peak RSS (MB) | threads | repeats | repeats consistent |
| ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 8 | 0 | 0 | 2 | 6 | true | `2x10bp@0` | 0.207 | 24 | 24 | 16.05 | 8 | 3 | true |
| 8 | 0 | 1 | 2 | 6 | true | `2x10bp@0` | 0.219 | 26 | 26 | 16.1 | 8 | 3 | true |
| 8 | 1 | 0 | 2 | 6 | true | `2x10bp@0` | 0.202 | 36 | 36 | 16.45 | 8 | 3 | true |
| 8 | 1 | 1 | 2 | 150 | true | `2x10bp@1` | 0.414 | 37 | 37 | 18.95 | 8 | 3 | true |
| 8 | 2 | 0 | 2 | 150 | true | `2x10bp@1` | 0.213 | 36 | 36 | 18.58 | 8 | 3 | true |
| 8 | 2 | 1 | 2 | 1662 | true | `2x10bp@2` | 2.366 | 38 | 38 | 32.3 | 8 | 3 | true |
| 8 | 3 | 0 | 2 | 150 | true | `2x10bp@1` | 0.398 | 36 | 36 | 18.81 | 8 | 3 | true |
| 8 | 3 | 1 | 2 | 10734 | true | `2x10bp@3` | 12.404 | 67 | 67 | 93.09 | 8 | 3 | true |
| 10 | 0 | 0 | 2 | 2 | true | `2x10bp@0` | 0.212 | 24 | 24 | 15.42 | 8 | 3 | true |
| 10 | 0 | 1 | 2 | 2 | true | `2x10bp@0` | 0.205 | 26 | 26 | 15.68 | 8 | 3 | true |
| 10 | 1 | 0 | 2 | 2 | true | `2x10bp@0` | 0.219 | 36 | 36 | 23.59 | 8 | 3 | true |
| 10 | 1 | 1 | 2 | 62 | true | `2x10bp@1` | 0.219 | 37 | 37 | 24.04 | 8 | 3 | true |
| 10 | 2 | 0 | 2 | 62 | true | `2x10bp@1` | 0.209 | 36 | 36 | 16.99 | 8 | 3 | true |
| 10 | 2 | 1 | 2 | 872 | true | `2x10bp@2` | 0.306 | 38 | 38 | 26.37 | 8 | 3 | true |
| 10 | 3 | 0 | 2 | 62 | true | `2x10bp@1` | 0.207 | 36 | 36 | 23.93 | 8 | 3 | true |
| 10 | 3 | 1 | 2 | 7352 | true | `2x10bp@3` | 1.082 | 66 | 66 | 31.8 | 8 | 3 | true |

Index builds, one per k [docs/seed_plan_sweep.json:index_builds]:

| k | threads | build time (s) | index bytes | position dtype | total bases |
| ---: | ---: | ---: | ---: | --- | ---: |
| 8 | 8 | 0.955 | 4524314 | `u4` | 1000000 |
| 10 | 8 | 0.316 | 12388602 | `u4` | 1000000 |

## Table S3

Cross-engine benchmark, merging the exact-match and bulge-overhead tables of
`example/engine_benchmark_small/REPORT.md`. Fixture: synthetic 1,000,000 bp genome,
12 guides of 20 nt, 24 planted exact hits, 8 threads, median of 3 repeated searches.
Exact-match rows use `max_mismatch=0, max_bulge=0`; bulge rows use
`max_mismatch=0, max_bulge=1`.

| engine | build/index, exact (s) | warm search, exact (s) | build + warm, exact (s) | hits, exact | build/index, bulge (s) | warm search, bulge (s) | build + warm, bulge (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| native-indexed | 0.107 | 0.048 | 0.155 | 24 | 0.095 | 0.183 | 0.278 |
| blast | 0.060 | 0.518 | 0.578 | 24 | 0.099 | 0.565 | 0.664 |
| bowtie2 | 0.902 | 0.176 | 1.078 | 24 | 0.886 | 0.176 | 1.062 |
| indexed, Python | 0.178 | 0.990 | 1.168 | 24 | 0.182 | 8.729 | 8.911 |
| casoffinder | no persistent build | 1.547 | 1.547 | 24 | n/a | n/a | n/a |
| exact | no persistent build | 2.156 | 2.156 | 24 | no persistent build | 2.617 | 2.617 |

Notes. `exact` builds an in-memory search structure on every call, so its search
time is not comparable to a warm persistent-index search [REPORT.md:22-23]. The
fixture does not plant a true bulge hit, so the bulge columns measure the cost of
enabling bulge search rather than bulge recall [REPORT.md:38-39]. Cas-OFFinder is
absent from the bulge block because the backend rejects bulge requests
[REPORT.md:28-30]. Recall is reported separately: in a 1-mismatch stress run the
exact, indexed, native-indexed and Cas-OFFinder backends each returned 36 of 36
hits, while BLAST returned 31 of 36 because its local alignment extension truncated
some one-mismatch 20 nt alignments [REPORT.md:52-54].

## Table S4

Model inventory and calibration status, from `docs/MODELS.md`. Sizes are the on-disk
file sizes recorded in that document.

| model key | file | format | size | registry status | runtime status |
| --- | --- | --- | ---: | --- | --- |
| `crispr_m` | `tcrispr_model.h5` | Keras HDF5 weights | 20,820,808 B | `ready` | available; pure NumPy forward verified, sample output 0.6321092247962952 [MODELS.md:7,26] [30] |
| `deepcrispr` | `deepcrispr_offtar_pt_cnn_reg.tar.gz` | TensorFlow 1.x checkpoint (tar.gz) | 29,160,245 B (unpacked data 44,228,628 B) | `ready` (file only) | needs TensorFlow; superseded by the portable file below [MODELS.md:8,29-47] |
| `deepcrispr` | `deepcrispr_offtar_pt_cnn_reg.portable.npz` | NumPy weights (67 tensors) | 14,778,336 B | - | available; maximum output error against the TensorFlow reference graph 2.98e-7 over 100 official examples [MODELS.md:9,47] [28] |
| `azimuth` | `azimuth_V3_model_nopos.pickle` | legacy scikit-learn pickle (GradientBoostingRegressor) | 135,380 B | `ready` (file only) | needs scikit-learn 1.0.2; superseded by the portable file below [MODELS.md:10,64-77] |
| `azimuth` | `azimuth_V3_model_nopos.portable.npz` | NumPy GBDT (100 trees) plus feature order | 194,548 B | - | available; Spearman 0.993 and MAE 0.0073 against the official 1000-guide reference, 561 of 947 compared rows identical [MODELS.md:11,77-81] [27] |
| `teep` | no local file | online HTTP API | - | `web_api` | available but network-dependent; no local weights, cache or version pin [MODELS.md:12,144-148] |

Notes. `TIGER` (Cas13d) ships as a TensorFlow SavedModel under `models/tiger/` and
is loaded through a version-independent path [MODELS.md:84-136]. `DeepCpf1`
(`seq_deepcpf1_weights.h5`) is a further ported model, described in `docs/MODELS.md`
[MODELS.md:49-62] and scored in the results, whose original paper is ref. [29]; it is
not a row of the inventory table above, which reproduces `docs/MODELS.md` verbatim.
Calibration state
propagates into the result tables: substitution-only hits scored by a reference model
are labelled `calibrated_reference`, bulge hits carry the versioned conservative
penalty `conservative_bulge_v1` and are labelled `uncalibrated`, as are the generic
heuristics [PAPER_METHODS_DRAFT.md:2.8]. Table S4 is a snapshot of
`docs/MODELS.md`; the registry status vocabulary is defined there
[`not_downloaded`, `load_error`, `ready`, `prediction_error`, MODELS.md:174-181].

## Table S5

Output field contract, from `docs/OUTPUTS.md`. Each scoring run writes three main
tables - the sorted score table, the unique-guide table and the top off-target table
- and a column is omitted when it is empty for the whole run
[OUTPUTS.md:11-33]. Model columns are written per selected model as
`on_target_score_<model>` and `off_target_specificity_<model>`; a model name does not
occupy a column of its own [OUTPUTS.md:11-33].

| group | columns | when written |
| --- | --- | --- |
| Common statistics | `rank`, `nuclease`, `total_matches`, `valid_matches`, `sum_mismatch`, `MM0` ... `MMn`, `GC-content`, `GC-hint`, `Self-complementarity`, `Self-comp-hint`, `legacy_total_score`, `pos_id`, `seq_id`, `strand`, `motif_pos`, `qid`, `query_seq` | every run; `MM0` to `MMn` follows `max_mismatch`, the last bucket merges `>= n` [OUTPUTS.md:86-104] |
| Annotation | `Annotation`, `Nearest-TSS`, `Isoforms`, `Downstream-ATG` | only when a GFF annotation is supplied [OUTPUTS.md:86-104] |
| Specificity and on-target | `off_target_specificity`, `off_target_specificity_<model>`, `on_target_score_<model>`, `crispai_aggregate_score` | per selected model; the unsuffixed specificity is the main score of the single-motif and unique-guide tables [OUTPUTS.md:106-118] |
| Bulge and calibration | `input_offtargets`, `substitution_offtargets`, `bulge_hits`, `scored_bulge_hits`, `unscored_bulge_hits`, `bulge_risk_sum`, `bulge_score_method`, `calibration_status` | when hits are scored; `bulge_hits = scored_bulge_hits + unscored_bulge_hits` holds by construction, and `bulge_score_method` is `conservative_bulge_v1` [OUTPUTS.md:120-128] |
| TnpB and RNA sub-features | `on_target_score_omega`, `on_target_score_teep`, `off_target_specificity_identity`, `spacer_len_score`, `guide_structure_penalty`, `repeat_hairpin_score`, `AT_score`, `guide_mfe`, `guide_accessibility`, `target_accessibility`, `dr_spacer_duplex_mfe`, `dr_spacer_penalty`, `perturbation_mfe`, `dr_source` | only with the corresponding on-target model selected [OUTPUTS.md:130-145] |
| Pair ranking (paired layouts) | `pair_id`, `pair_rank`, `pair_rank_status`, `pair_rank_mode`, `pair_rank_key`, `pair_activity_tier`, `left_activity_tier`, `right_activity_tier`, `left_eligible_model_count`, `right_eligible_model_count`, `pair_offtarget_burden`, `pair_max_offtarget_upper`, `pair_high_risk_count`, `pair_activity_disagreement`, `pair_compatibility_penalty`, `pair_gate_reasons`, `conditional_rank` | paired layouts only; `pair_rank_mode` is `prediction_only` [OUTPUTS.md:147-171] |
| Retired | `combined_score`, `left_rank`, `right_rank`, `on_target_model_*`, `off_target_model_*`, `rna_model`, `omega_model`, `reference_only`, fixed sub-feature columns | not emitted; their presence identifies an older result file [OUTPUTS.md:173-193] |

Notes. The `experiment_calibrated` pair-ranking fields are a documented target
contract and are not produced by the current pipeline [OUTPUTS.md:173-193].
`--xlsx` and BED writers are opt-in, and the GUI run label renames the three main
tables without changing their columns [OUTPUTS.md:11-33].

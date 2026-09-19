# Reference list (numbered)

Numbered literature references for the `manuscript-v1` draft. Numbering follows the
order of the precedent table in `docs/PAPER_OUTLINE.md` section 2.1 for [1]-[20], so
that every precedent has a stable number; [21]-[24] are the published tools that
appear in the capability matrix of `docs/expressiveness_matrix.tsv` but not in the
precedent table, [25]-[26] are the TnpB papers recorded in `docs/TNPB.md`, and
[27]-[30] are the original papers of the four published models that this platform
ports and checks against their reference outputs.

Reference discipline for this draft (round-1 contract C4): the permitted set is the
precedent table of `docs/PAPER_OUTLINE.md` section 2.1 (20 entries with DOI), the
tools recorded in `docs/expressiveness_matrix.tsv`, the TnpB literature recorded in
`docs/TNPB.md` and `docs/MODELS.md`, and literature already present in the
repository. No reference outside that set is included in [1]-[26]. The DOI of every
entry in [1]-[26] comes from one of those repository sources; the bibliographic
fields - authors, title, journal, year, volume, issue and pages - were resolved from
that DOI through the Europe PMC REST interface on 2026-09-19, the same literature
channel that `docs/PAPER_OUTLINE.md` section 0 records. Every entry has a resolvable
DOI and no field is invented.

Round 2 adds one directed widening of that set, authorised by master for four entries
only. Entries [27]-[30] are the original papers of the four published models whose
ports and reference checks are reported in the scoring results; no other entry lies
outside the permitted set. The DOI source of each of the four is recorded in its
entry comment.

Two works are named in the repository but are not numbered here because no DOI is
recorded for them: `sgRNA Scorer 2.0`, named in `docs/PAPER_OUTLINE.md` section 1.1,
and `Endo et al. 2015`, named in `docs/ALLEGRO_REFERENCE_ANALYSIS.md` section 4.1.
Neither is cited in the draft text.

## References

[1] Pulido-Quetglas C, Aparicio-Prat E, Arnan C, Polidori T, Hermoso T, Palumbo E, Ponomarenko J, Guigo R, Johnson R. Scalable Design of Paired CRISPR Guide RNAs for Genomic Deletion. PLoS Comput Biol 2017;13(3):e1005341. doi:10.1371/journal.pcbi.1005341 <!-- CRISPETa; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[2] Xiong Y, Xie X, Wang Y, Ma W, Liang P, Songyang Z, Dai Z. pgRNAFinder: a web-based tool to design distance independent paired-gRNA. Bioinformatics 2017;33(22):3642-3644. doi:10.1093/bioinformatics/btx472 <!-- pgRNAFinder; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[3] Perez AR, Pritykin Y, Vidigal JA, Chhangawala S, Zamparo L, Leslie CS, Ventura A. GuideScan software for improved single and paired CRISPR guide RNA design. Nat Biotechnol 2017;35(4):347-349. doi:10.1038/nbt.3804 <!-- GuideScan; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[4] O'Brien A, Bailey TL. GT-Scan: identifying unique genomic targets. Bioinformatics 2014;30(18):2673-2675. doi:10.1093/bioinformatics/btu354 <!-- GT-Scan; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[5] Aparicio-Prat E, Arnan C, Sala I, Bosch N, Guigó R, Johnson R. DECKO: Single-oligo, dual-CRISPR deletion of genomic elements including long non-coding RNAs. BMC Genomics 2015;16:846. doi:10.1186/s12864-015-2086-z <!-- DECKO; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[6] Park J, Bae S, Kim JS. Cas-Designer: a web-based tool for choice of CRISPR-Cas9 target sites. Bioinformatics 2015;31(24):4014-4016. doi:10.1093/bioinformatics/btv537 <!-- Cas-Designer; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[7] McKenna A, Shendure J. FlashFry: a fast and flexible tool for large-scale CRISPR target design. BMC Biol 2018;16(1):74. doi:10.1186/s12915-018-0545-0 <!-- FlashFry; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[8] Cancellieri S, Canver MC, Bombieri N, Giugno R, Pinello L. CRISPRitz: rapid, high-throughput and variant-aware in silico off-target site identification for CRISPR genome editing. Bioinformatics 2020;36(7):2001-2008. doi:10.1093/bioinformatics/btz867 <!-- CRISPRitz; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[9] Labun K, Montague TG, Krause M, Torres Cleuren YN, Tjeldnes H, Valen E. CHOPCHOP v3: expanding the CRISPR web toolbox beyond genome editing. Nucleic Acids Res 2019;47(w1):W171-W174. doi:10.1093/nar/gkz365 <!-- CHOPCHOP v3; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[10] Hoberecht L, Perampalam P, Lun A, Fortin JP. A comprehensive Bioconductor ecosystem for the design of CRISPR guide RNAs across nucleases and technologies. Nat Commun 2022;13(1):6568. doi:10.1038/s41467-022-34320-7 <!-- crisprVerse; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[11] Asadbeigi A, Norouzi M, Vafaei Sadi MS, Saffari M, Bakhtiarizadeh MR. CaSilico: A versatile CRISPR package for in silico CRISPR RNA designing for Cas12, Cas13, and Cas14. Front Bioeng Biotechnol 2022;10:957131. doi:10.3389/fbioe.2022.957131 <!-- CaSilico; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[12] Bae S, Park J, Kim JS. Cas-OFFinder: a fast and versatile algorithm that searches for potential off-target sites of Cas9 RNA-guided endonucleases. Bioinformatics 2014;30(10):1473-1475. doi:10.1093/bioinformatics/btu048 <!-- Cas-OFFinder; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[13] Pliatsika V, Rigoutsos I. "Off-Spotter": very fast and exhaustive enumeration of genomic lookalikes for designing CRISPR/Cas guide RNAs. Biol Direct 2015;10:4. doi:10.1186/s13062-015-0035-z <!-- Off-Spotter; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[14] Marquart KF, Mathis N, Mollaysa A, Müller S, Kissling L, Rothgangl T, Schmidheini L, Kulcsár PI, Allam A, Kaufmann MM, Matsushita M, Haenggi T, Cathomen T, Kopf M, Krauthammer M, Schwank G. Effective genome editing with an enhanced ISDra2 TnpB system and deep learning-predicted ωRNAs. Nat Methods 2024;21(11):2084-2093. doi:10.1038/s41592-024-02418-z <!-- TEEP / TnpBmax; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[15] Prykhozhij SV, Rajan V, Gaston D, Berman JN. CRISPR multitargeter: a web tool to find common and unique CRISPR single guide RNA targets in a set of similar sequences. PLoS One 2015;10(3):e0119372. doi:10.1371/journal.pone.0119372 <!-- CRISPR multitargeter; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[16] Boob AG, Zhu Z, Intasian P, Jain M, Petrov VA, Lane ST, Tan SI, Xun G, Zhao H. CRISPR-COPIES: an in silico platform for discovery of neutral integration sites for CRISPR/Cas-facilitated gene integration. Nucleic Acids Res 2024;52(6):e30. doi:10.1093/nar/gkae062 <!-- CRISPR-COPIES; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[17] Mohseni A, Nia RG, Tafrishi A, López ML, Liu XZ, Stajich JE, Lonardi S, Wheeldon I. Kingdom-wide CRISPR guide design with ALLEGRO. Nucleic Acids Res 2025;53(15):gkaf783. doi:10.1093/nar/gkaf783 <!-- ALLEGRO; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[18] Lee RRQ, Cher WY, Wang J, Chen Y, Chae E. Generating minimum set of gRNA to cover multiple targets in multiple genomes with MINORg. Nucleic Acids Res 2023;51(8):e43. doi:10.1093/nar/gkad142 <!-- MINORg; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[19] Hyams G, Abadi S, Lahav S, Avni A, Halperin E, Shani E, Mayrose I. CRISPys: Optimal sgRNA Design for Editing Multiple Members of a Gene Family Using the CRISPR System. J Mol Biol 2018;430(15):2184-2195. doi:10.1016/j.jmb.2018.03.019 <!-- CRISPys; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[20] Bhagwat AM, Graumann J, Wiegandt R, Bentsen M, Welker J, Kuenne C, Preussner J, Braun T, Looso M. multicrispr: gRNA design for prime editing and parallel targeting of thousands of targets. Life Sci Alliance 2020;3(11):e202000757. doi:10.26508/lsa.202000757 <!-- multicrispr; DOI source: docs/PAPER_OUTLINE.md section 2.1 -->

[21] Schmidt H, Zhang M, Chakarov D, Bansal V, Mourelatos H, Sánchez-Rivera FJ, Lowe SW, Ventura A, Leslie CS, Pritykin Y. Genome-wide CRISPR guide RNA design and specificity analysis with GuideScan2. Genome Biol 2025;26(1):41. doi:10.1186/s13059-025-03488-8 <!-- GuideScan2; DOI source: docs/expressiveness_matrix.tsv line 7 -->

[22] Concordet JP, Haeussler M. CRISPOR: intuitive guide selection for CRISPR/Cas9 genome editing experiments and screens. Nucleic Acids Res 2018;46(w1):W242-W245. doi:10.1093/nar/gky354 <!-- CRISPOR; DOI source: docs/expressiveness_matrix.tsv line 4 -->

[23] Oliveros JC, Franch M, Tabas-Madrid D, San-León D, Montoliu L, Cubas P, Pazos F. Breaking-Cas-interactive design of guide RNAs for CRISPR-Cas experiments for ENSEMBL genomes. Nucleic Acids Res 2016;44(w1):W267-71. doi:10.1093/nar/gkw407 <!-- Breaking-Cas; DOI source: docs/expressiveness_matrix.tsv line 12 -->

[24] Peng D, Tarleton R. EuPaGDT: a web tool tailored to design CRISPR guide RNAs for eukaryotic pathogens. Microb Genom 2015;1(4):e000033. doi:10.1099/mgen.0.000033 <!-- EuPaGDT; DOI source: docs/expressiveness_matrix.tsv line 13 -->

[25] Karvelis T, Druteika G, Bigelyte G, Budre K, Zedaveinyte R, Silanskas A, Kazlauskas D, Venclovas Č, Siksnys V. Transposon-associated TnpB is a programmable RNA-guided DNA endonuclease. Nature 2021;599(7886):692-696. doi:10.1038/s41586-021-04058-1 <!-- TnpB (Karvelis et al.); DOI source: docs/TNPB.md lines 272-274; docs/MODELS.md lines 157-159 -->

[26] Altae-Tran H, Kannan S, Demircioglu FE, Oshiro R, Nety SP, McKay LJ, Dlakić M, Inskeep WP, Makarova KS, Macrae RK, Koonin EV, Zhang F. The widespread IS200/IS605 transposon family encodes diverse programmable RNA-guided endonucleases. Science 2021;374(6563):57-65. doi:10.1126/science.abj6856 <!-- IS200/IS605 nucleases (Altae-Tran et al.); DOI source: docs/TNPB.md lines 278-281; docs/MODELS.md lines 159-161 -->

[27] Doench JG, Fusi N, Sullender M, Hegde M, Vaimberg EW, Donovan KF, Smith I, Tothova Z, Wilen C, Orchard R, Virgin HW, Listgarten J, Root DE. Optimized sgRNA design to maximize activity and minimize off-target effects of CRISPR-Cas9. Nat Biotechnol 2016;34(2):184-191. doi:10.1038/nbt.3437 <!-- Azimuth (Doench et al.); DOI source: task.md section 8 item D3, resolved via Europe PMC REST 2026-09-19 -->

[28] Chuai G, Ma H, Yan J, Chen M, Hong N, Xue D, Zhou C, Zhu C, Chen K, Duan B, Gu F, Qu S, Huang D, Wei J, Liu Q. DeepCRISPR: optimized CRISPR guide RNA design by deep learning. Genome Biol 2018;19(1):80. doi:10.1186/s13059-018-1459-4 <!-- DeepCRISPR (Chuai et al.); DOI source: task.md section 8 item D3, resolved via Europe PMC REST 2026-09-19; author list cross-checked with Crossref -->

[29] Kim HK, Min S, Song M, Jung S, Choi JW, Kim Y, Lee S, Yoon S, Kim HH. Deep learning improves prediction of CRISPR-Cpf1 guide RNA activity. Nat Biotechnol 2018;36(3):239-241. doi:10.1038/nbt.4061 <!-- DeepCpf1 (Kim et al.); DOI source: task.md section 8 item D3, resolved via Europe PMC REST 2026-09-19 -->

[30] Sun J, Guo J, Liu J. CRISPR-M: Predicting sgRNA off-target effect using a multi-view deep learning network. PLoS Comput Biol 2024;20(3):e1011972. doi:10.1371/journal.pcbi.1011972 <!-- CRISPR-M (Sun et al.); DOI source: shared/scoring/model_registry.py MODELS["crispr_m"].url (github.com/lyotvincent/CRISPR-M), resolved via Europe PMC REST 2026-09-19 -->

## Citation coverage

Every entry is cited at least once in the draft body. The table records where.

| # | short name | cited in |
| ---: | --- | --- |
| [1] | CRISPETa | Introduction (paired-guide tools); Results, 'Motif-anchored design space and expressiveness' |
| [2] | pgRNAFinder | Introduction (paired-guide tools); Results, same subsection |
| [3] | GuideScan | Introduction (paired-guide tools) |
| [4] | GT-Scan | Introduction (paired-guide tools); Results, same subsection |
| [5] | DECKO | Introduction (paired-guide tools); Results, same subsection |
| [6] | Cas-Designer | Introduction (region/gene tools); Results, same subsection |
| [7] | FlashFry | Introduction (region/gene tools) |
| [8] | CRISPRitz | Introduction (region/gene tools); Discussion (seed strategy) |
| [9] | CHOPCHOP v3 | Introduction (region/gene tools); Results, same subsection |
| [10] | crisprVerse | Introduction (region/gene tools); Results, same subsection |
| [11] | CaSilico | Introduction (region/gene tools) |
| [12] | Cas-OFFinder | Introduction (off-target engines and engine gap) |
| [13] | Off-Spotter | Introduction (off-target engines and engine gap) |
| [14] | TEEP / TnpBmax | Introduction (effector predictors); Results, 'Scoring, calibration status and pair ranking' |
| [15] | CRISPR multitargeter | Introduction (library-scale design); Results, same subsection |
| [16] | CRISPR-COPIES | Introduction (library-scale design and approximate search) |
| [17] | ALLEGRO | Introduction (gap statement, quoted) |
| [18] | MINORg | Introduction (library-scale design) |
| [19] | CRISPys | Introduction (library-scale design) |
| [20] | multicrispr | Introduction (library-scale design) |
| [21] | GuideScan2 | Introduction (paired-guide tools); Discussion (seed strategy) |
| [22] | CRISPOR | Introduction (region/gene tools) |
| [23] | Breaking-Cas | Introduction (region/gene tools) |
| [24] | EuPaGDT | Introduction (region/gene tools); Results, same subsection |
| [25] | TnpB (Karvelis et al.) | Introduction (TAM-level effectors); Results, 'Scoring, calibration status and pair ranking' |
| [26] | IS200/IS605 nucleases (Altae-Tran et al.) | Introduction (TAM-level effectors); Results, same subsection |
| [27] | Azimuth | Results, 'Scoring, calibration status and pair ranking'; Table S4 |
| [28] | DeepCRISPR | Results, same subsection; Table S4 |
| [29] | DeepCpf1 | Results, same subsection; Table S4 (notes) |
| [30] | CRISPR-M | Results, same subsection; Table S4 |

Coverage checks:

- All 20 entries of the precedent table, [1]-[20], are cited in the draft body.
- [21] (GuideScan2) and [22] (CRISPOR) are cited in the Introduction; [23]
  (Breaking-Cas) and [24] (EuPaGDT) are cited in the Introduction and in the
  capability-matrix results.
- [25] and [26] are cited in the Introduction and in the scoring results.
- [14] (TEEP / TnpBmax) is cited in the Introduction and in the scoring results.
- [27]-[30] are cited in the scoring results; all four also appear in Table S4
  ([27], [28] and [30] on the corresponding model rows, [29] in the notes).

## Open item

The round-1 contract recommends 45-70 references. The permitted source set above
supports 26 entries with a resolvable DOI, and the round-2 directed widening adds the
four model papers [27]-[30]; reaching the recommended range would still require citing
literature that is not in the repository, which the same contract forbids. The count
is therefore 30, and the remaining gap is reported to master rather than filled by
widening the source set further.

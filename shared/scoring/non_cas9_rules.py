#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rule tables for non-Cas9 CRISPR systems.

Each rule row records the experimentally reported PAM/PFS, seed positions,
mismatch tolerance, cleavage behaviour and the literature source so scores
produced from the table can be traced back to a reference.
"""


NON_CAS9_RULES = {
    "cas12a": {
        "label": "Cas12a (LbCpf1)",
        "pam": "TTTN",
        "pam_side": "5prime",
        "spacer_len": 24,
        "seed_start": 1,
        "seed_end": 6,
        "seed_penalty": 0.25,
        "non_seed_penalty": 0.0,
        "max_mismatch_hint": 4,
        "bulge_tolerance": 1,
        "cleavage": "Staggered cuts ~18-23 nt distal from PAM on the "
                    "non-target strand and ~5-18 nt on the target strand.",
        "target_type": "dna",
        "source": "Zetsche et al. 2015, Cell",
        "source_url": "https://doi.org/10.1016/j.cell.2015.09.038",
        "notes": "CHOPCHOP Cpf1 default: 24 nt spacer with a TTTN 5' PAM. "
                 "PAM-proximal seed positions 1-6; distal mismatches are "
                 "tolerated more readily. The stricter AsCpf1/LbCpf1 PAM is "
                 "TTTV (V=A/C/G), a subset of TTTN.",
    },
    "cas12b": {
        "label": "Cas12b (AapCas12b)",
        "pam": "TTN",
        "pam_side": "5prime",
        "spacer_len": 20,
        "seed_start": 1,
        "seed_end": 20,
        "seed_penalty": 0.5,
        "non_seed_penalty": 0.0,
        "max_mismatch_hint": 4,
        "bulge_tolerance": 1,
        "cleavage": "Staggered cuts distal to the PAM; exact offsets vary by "
                    "orthologue and guide length.",
        "target_type": "dna",
        "source": "Strecker et al. 2019, Nature Communications",
        "source_url": "https://doi.org/10.1038/s41467-019-10336-2",
        "notes": "Broad mismatch tolerance across the spacer in several "
                 "Cas12b orthologues.",
    },
    "cas14a": {
        "label": "Cas14a",
        "pam": "",
        "pam_side": "",
        "spacer_len": 20,
        "seed_start": 9,
        "seed_end": 16,
        "seed_penalty": 0.25,
        "non_seed_penalty": 0.0,
        "max_mismatch_hint": 4,
        "bulge_tolerance": 1,
        "cleavage": "Site-specific cleavage of single-stranded DNA; cleavage "
                    "sites are defined relative to the guide duplex.",
        "target_type": "ssdna",
        "source": "Harrington et al. 2018, Science",
        "source_url": "https://doi.org/10.1126/science.aav4294",
        "notes": "No PAM requirement reported for Cas14a.",
    },
    "cas13": {
        "label": "Cas13 (CHOPCHOP)",
        "pam": "H",
        "pam_side": "5prime",
        "spacer_len": 27,
        "seed_start": None,
        "seed_end": None,
        "seed_penalty": 0.3,
        "non_seed_penalty": 0.0,
        "max_mismatch_hint": 4,
        "bulge_tolerance": 1,
        "cleavage": "RNA cleavage guided by the spacer; collateral RNA cleavage "
                    "occurs after target recognition.",
        "target_type": "rna",
        "source": "CHOPCHOP v3; Abudayyeh et al. 2017, Nature",
        "source_url": "https://chopchop.cbu.uib.no/",
        "notes": "CHOPCHOP Cas13 default: 27 nt spacer with a 5' non-G flanking "
                 "site (H = A/C/T). Subtype-specific constructs (Cas13a/b/d) "
                 "require their own direct repeat, supplied by the user.",
    },
    "tnpb": {
        "label": "TnpB / omegaRNA",
        "pam": "TAM",
        "pam_side": "5prime",
        "spacer_len": None,
        "seed_start": None,
        "seed_end": None,
        "seed_penalty": 0.25,
        "non_seed_penalty": 0.0,
        "max_mismatch_hint": 4,
        "bulge_tolerance": 1,
        "cleavage": "TnpB uses a single omegaRNA with repeat and spacer-like "
                    "regions to nick or cut DNA at a TAM-proximal site.",
        "target_type": "dna",
        "source": "Karvelis et al. 2021, Nature",
        "source_url": "https://doi.org/10.1038/s41586-021-04058-1",
        "notes": "Rule table is a local stand-in for the online TEEP service. "
                 "ISDra2 literature defines a 5'-TTGAT TAM; the preset "
                 "value 'TAM' is a configurable motif string, not a complete "
                 "substitute for that canonical motif.",
    },
}


def get_rules(key):
    """Return the rule dict for a preset, or None for Cas9/custom rules."""
    key = (key or "custom").lower()
    if key in ("custom", "cas9"):
        return None
    return NON_CAS9_RULES.get(key)


def rule_source(key):
    rules = get_rules(key)
    return rules["source"] if rules else ""


def rule_summary_text(key):
    rules = get_rules(key)
    if not rules:
        return ""
    parts = []
    if rules.get("pam"):
        parts.append("PAM/PFS %s (%s)" % (rules["pam"], rules["pam_side"]))
    if rules.get("seed_start") is not None and rules.get("seed_end") is not None:
        parts.append("seed %s-%s" % (rules["seed_start"], rules["seed_end"]))
    if rules.get("cleavage"):
        parts.append(rules["cleavage"])
    parts.append("source: %s" % rules["source"])
    return "; ".join(parts)

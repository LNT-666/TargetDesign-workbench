"""AT-content scoring helpers shared by single and paired motif pipelines."""


def compute_at_score_from_flank(flank_seq, side, strand):
    """Score a raw flank after orienting it relative to the guide."""
    flank_seq = flank_seq or ""
    flank_len = len(flank_seq)
    if side == "upstream":
        oriented = flank_seq if strand == "plus" else flank_seq[::-1]
    else:
        oriented = flank_seq[::-1] if strand == "plus" else flank_seq
    return sum(
        flank_len - 1 - index
        for index, base in enumerate(oriented)
        if base in "AT"
    )


def compute_at_score(query_seq, side, strand, motif_plus, motif_minus,
                     flank_len):
    """Return the legacy AT score for a guide-oriented query window."""
    motif_len = len(motif_plus)
    if side == "upstream":
        flank_seq = (
            query_seq[:flank_len]
            if strand == "plus"
            else query_seq[motif_len:]
        )
    else:
        flank_seq = (
            query_seq[motif_len:]
            if strand == "plus"
            else query_seq[:flank_len]
        )
    return compute_at_score_from_flank(flank_seq, side, strand)


def should_output_at_score(mode, preset, side_preset=None):
    """Return whether AT score output is enabled for a system selection."""
    selected_preset = preset if side_preset is None else side_preset
    selected_mode = "preset" if side_preset is not None else mode
    return (
        str(selected_mode or "").strip().lower() == "preset"
        and str(selected_preset or "").strip().lower() == "tnpb"
    )

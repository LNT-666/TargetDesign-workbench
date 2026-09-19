#include "offtarget/search.hpp"

#include "offtarget/alignment.hpp"
#include "offtarget/error.hpp"
#include "offtarget/json_writer.hpp"
#include "offtarget/pam.hpp"
#include "offtarget/seed_plan.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <exception>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#ifdef _WIN32
#define NOMINMAX
#include <Windows.h>
#include <Psapi.h>
#else
#include <cstdio>
#include <unistd.h>
#endif

namespace offtarget {

namespace {

constexpr std::uint64_t kMaxExhaustiveFallbackBases = 50000000ULL;
constexpr int kDefaultContext = 40;
constexpr std::uint64_t kMiB = 1024ULL * 1024ULL;
constexpr std::uint64_t kAutoCacheReservedMemoryMb = 2048ULL;
constexpr std::uint64_t kAutoCacheWorkerOverheadMb = 16ULL;
constexpr std::uint64_t kAutoCacheMemoryDivisor = 2ULL;
constexpr std::uint64_t kFixedSearchOverheadMb = 128ULL;
constexpr std::uint64_t kSearchWorkerOverheadMb = 24ULL;
constexpr std::uint64_t kSearchWorkspaceMb = 32ULL;
constexpr std::uint64_t kMemoryCheckInterval = 256ULL;

std::optional<std::uint64_t> available_memory_mb();

std::uint64_t saturating_add(std::uint64_t left,
                            std::uint64_t right) noexcept {
    if (left > std::numeric_limits<std::uint64_t>::max() - right) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return left + right;
}

std::uint64_t saturating_multiply(std::uint64_t left,
                                  std::uint64_t right) noexcept {
    if (left != 0 &&
        right > std::numeric_limits<std::uint64_t>::max() / left) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return left * right;
}

std::uint64_t bytes_to_mb_ceil(std::uint64_t bytes) noexcept {
    return bytes / kMiB + (bytes % kMiB == 0 ? 0ULL : 1ULL);
}

std::uint64_t estimate_search_peak_mb(
    std::uint64_t genome_bytes, std::uint64_t index_bytes,
    std::uint64_t worker_count, std::uint64_t guide_count,
    bool use_sequence_cache) noexcept {
    std::uint64_t per_worker = kSearchWorkerOverheadMb;
    if (use_sequence_cache) {
        const std::uint64_t cache_bytes =
            saturating_add(genome_bytes, genome_bytes / 4ULL);
        per_worker = saturating_add(
            per_worker, bytes_to_mb_ceil(cache_bytes));
    }
    std::uint64_t estimate = saturating_add(
        kFixedSearchOverheadMb, bytes_to_mb_ceil(index_bytes));
    estimate = saturating_add(
        estimate, saturating_multiply(worker_count, per_worker));
    estimate = saturating_add(estimate, kSearchWorkspaceMb);
    return saturating_add(
        estimate, saturating_add(guide_count / 1024ULL, 1ULL));
}

[[noreturn]] void throw_memory_limit(
    std::uint64_t limit_mb, std::uint64_t estimated_peak_mb,
    const std::string& stage) {
    throw OfftargetError(
        ExitCode::memory_limit, "MEMORY_LIMIT_EXCEEDED",
        "Memory limit exceeded during " + stage + ": estimated peak " +
            std::to_string(estimated_peak_mb) + " MiB exceeds --max-memory-mb=" +
            std::to_string(limit_mb) + " MiB");
}

class MemoryGuard {
public:
    MemoryGuard(std::uint64_t limit_mb, std::atomic<bool>& cancelled,
                std::atomic<double>& observed_peak_mb)
        : limit_mb_(limit_mb),
          cancelled_(cancelled),
          observed_peak_mb_(observed_peak_mb) {}

    void check() {
        const double current = current_rss_mb();
        double observed = observed_peak_mb_.load(std::memory_order_relaxed);
        while (current > observed &&
               !observed_peak_mb_.compare_exchange_weak(
                   observed, current, std::memory_order_relaxed)) {
        }
        if (limit_mb_ > 0 &&
            current > static_cast<double>(limit_mb_)) {
            cancelled_.store(true, std::memory_order_relaxed);
            throw OfftargetError(
                ExitCode::memory_limit, "MEMORY_LIMIT_EXCEEDED",
                "Memory limit exceeded during search: RSS " +
                    std::to_string(current) +
                    " MiB exceeds --max-memory-mb=" +
                    std::to_string(limit_mb_) + " MiB");
        }
        if (cancelled_.load(std::memory_order_relaxed)) {
            throw OfftargetError(
                ExitCode::memory_limit, "MEMORY_LIMIT_CANCELLED",
                "Search cancelled because another worker exceeded the "
                "memory limit");
        }
    }

    void checkpoint(std::uint64_t counter) {
        if (counter % kMemoryCheckInterval == 0) {
            check();
        }
    }

private:
    std::uint64_t limit_mb_ = 0;
    std::atomic<bool>& cancelled_;
    std::atomic<double>& observed_peak_mb_;
};

class GenomeSource {
public:
    GenomeSource(const FastaFile& fasta, bool use_cache)
        : fasta_(fasta), use_cache_(use_cache) {}

    [[nodiscard]] bool use_cache() const noexcept { return use_cache_; }

    std::optional<std::string> fetch(const std::string& name,
                                     std::uint64_t start,
                                     std::uint64_t end) {
        if (!use_cache_) {
            return fasta_.fetch(name, start, end);
        }
        const FastaRecord* record = fasta_.find_record(name);
        if (record == nullptr) {
            return std::nullopt;
        }
        if (start >= record->length || end <= start) {
            return std::nullopt;
        }
        end = std::min(end, record->length);
        const std::string* sequence = sequence_for(name);
        if (sequence == nullptr || start >= end ||
            start >= sequence->size()) {
            return std::nullopt;
        }
        return sequence->substr(static_cast<std::size_t>(start),
                                static_cast<std::size_t>(end - start));
    }

    std::optional<std::string> fetch_all(const std::string& name) {
        if (!use_cache_) {
            return fasta_.fetch_all(name);
        }
        const std::string* sequence = sequence_for(name);
        if (sequence == nullptr) {
            return std::nullopt;
        }
        return *sequence;
    }

private:
    const std::string* sequence_for(const std::string& name) {
        const auto iterator = sequences_.find(name);
        if (iterator != sequences_.end()) {
            return &iterator->second;
        }
        std::optional<std::string> sequence = fasta_.fetch_all(name);
        if (!sequence.has_value()) {
            return nullptr;
        }
        const auto inserted =
            sequences_.emplace(name, std::move(*sequence));
        return &inserted.first->second;
    }

    const FastaFile& fasta_;
    bool use_cache_ = false;
    std::unordered_map<std::string, std::string> sequences_;
};

struct CandidateKey {
    std::string target;
    std::uint64_t local_start = 0;
    char strand = '+';

    bool operator==(const CandidateKey& other) const noexcept {
        return target == other.target &&
               local_start == other.local_start &&
               strand == other.strand;
    }
};

struct CandidateKeyHash {
    std::size_t operator()(const CandidateKey& key) const noexcept {
        std::size_t value = std::hash<std::string>{}(key.target);
        value ^= std::hash<std::uint64_t>{}(key.local_start) +
                 (value << 6U) + (value >> 2U);
        value ^= std::hash<char>{}(key.strand) + (value << 6U) +
                 (value >> 2U);
        return value;
    }
};

struct HitKey {
    std::string target;
    std::uint64_t target_start = 0;
    std::uint64_t target_end = 0;
    char strand = '+';

    bool operator==(const HitKey& other) const noexcept {
        return target == other.target &&
               target_start == other.target_start &&
               target_end == other.target_end &&
               strand == other.strand;
    }
};

struct HitKeyHash {
    std::size_t operator()(const HitKey& key) const noexcept {
        std::size_t value = std::hash<std::string>{}(key.target);
        value ^= std::hash<std::uint64_t>{}(key.target_start) +
                 (value << 6U) + (value >> 2U);
        value ^= std::hash<std::uint64_t>{}(key.target_end) +
                 (value << 6U) + (value >> 2U);
        value ^= std::hash<char>{}(key.strand) + (value << 6U) +
                 (value >> 2U);
        return value;
    }
};

std::string strip_cr(std::string line) {
    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }
    return line;
}

std::vector<std::string> parse_tsv_line(const std::string& line) {
    std::vector<std::string> fields;
    std::string current;
    bool quoted = false;
    for (std::size_t index = 0; index < line.size(); ++index) {
        const char ch = line[index];
        if (quoted) {
            if (ch == '"') {
                if (index + 1 < line.size() && line[index + 1] == '"') {
                    current.push_back('"');
                    ++index;
                } else {
                    quoted = false;
                }
            } else {
                current.push_back(ch);
            }
        } else if (ch == '"') {
            quoted = true;
        } else if (ch == '\t') {
            fields.push_back(std::move(current));
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    fields.push_back(std::move(current));
    return fields;
}

std::string normalize_probe(std::string sequence) {
    sequence = uppercase_ascii(std::move(sequence));
    for (char& ch : sequence) {
        if (ch == 'U') {
            ch = 'T';
        }
    }
    return sequence;
}

Hit alignment_to_hit(const AlignmentRecord& alignment,
                     const std::string& seqid,
                     std::uint64_t genomic_start,
                     const std::string& strand) {
    const std::uint64_t target_start =
        genomic_start + static_cast<std::uint64_t>(
                            std::max<std::int64_t>(
                                0, alignment.target_start));
    const std::uint64_t target_end =
        genomic_start + static_cast<std::uint64_t>(
                            std::max<std::int64_t>(
                                0, alignment.target_end));
    std::string query_aligned = alignment.query_aligned;
    std::string target_aligned = alignment.target_aligned;
    if (strand == "-") {
        query_aligned = reverse_complement_gapped(query_aligned);
        target_aligned = reverse_complement_gapped(target_aligned);
    }

    std::string operations;
    operations.reserve(std::max(query_aligned.size(),
                                target_aligned.size()));
    int mismatches = 0;
    for (std::size_t index = 0;
         index < std::min(query_aligned.size(), target_aligned.size());
         ++index) {
        const char query_base = query_aligned[index];
        const char target_base = target_aligned[index];
        if (query_base == '-' && target_base != '-') {
            operations.push_back('D');
        } else if (target_base == '-' && query_base != '-') {
            operations.push_back('I');
        } else if (query_base == target_base) {
            operations.push_back('M');
        } else {
            operations.push_back('X');
            ++mismatches;
        }
    }
    const int rna_bulges =
        static_cast<int>(std::count(operations.begin(), operations.end(),
                                    'I'));
    const int dna_bulges =
        static_cast<int>(std::count(operations.begin(), operations.end(),
                                    'D'));
    int query_len = 0;
    for (const char base : query_aligned) {
        if (base != '-') {
            ++query_len;
        }
    }

    Hit hit;
    hit.target = seqid;
    hit.start = target_start;
    hit.strand = strand;
    hit.mismatch = mismatches;
    hit.indel = rna_bulges + dna_bulges;
    hit.rna_bulges = rna_bulges;
    hit.dna_bulges = dna_bulges;
    hit.cigar = cigar_from_operations(operations);
    hit.target_start = target_start;
    hit.target_end = target_end;
    hit.query_start = 0;
    hit.query_end = query_len;
    hit.aligned_guide = std::move(query_aligned);
    hit.aligned_target = std::move(target_aligned);
    hit.bitscore = std::max(
        0.0, 100.0 - alignment.mismatches * 12.0 -
                 alignment.indels() * 18.0);
    hit.engine = "indexed";
    return hit;
}

bool hit_less(const Hit& left, const Hit& right) {
    if (left.mismatch != right.mismatch) {
        return left.mismatch < right.mismatch;
    }
    if (left.indel != right.indel) {
        return left.indel < right.indel;
    }
    if (left.target != right.target) {
        return left.target < right.target;
    }
    if (left.start != right.start) {
        return left.start < right.start;
    }
    return left.target_end < right.target_end;
}

std::uint64_t locate_or_none(const GenomeIndex& index,
                             std::uint64_t global_position,
                             std::string& target,
                             std::uint64_t& local_start) {
    const auto located = index.locate(global_position);
    if (!located.has_value()) {
        return 0;
    }
    target = located->first;
    local_start = located->second;
    return 1;
}

std::uint64_t decode_position(
    const std::span<const std::uint8_t> positions,
    std::size_t position_index, std::size_t width) {
    const std::uint8_t* bytes =
        positions.data() + position_index * width;
    std::uint64_t value = 0;
    for (std::size_t byte = 0; byte < width; ++byte) {
        value |= static_cast<std::uint64_t>(bytes[byte]) << (8U * byte);
    }
    return value;
}

std::vector<Hit> search_probe(
    const GenomeIndex& index, GenomeSource& genome,
    const std::string& probe, const std::string& target_strand,
    int max_mismatch, int max_bulge, int seed_len,
    const std::optional<std::string>& pam,
    const std::string& pam_side, MemoryGuard& memory_guard) {
    std::vector<Hit> hits;
    const int probe_len = static_cast<int>(probe.size());
    if (probe_len < static_cast<int>(index.k())) {
        return hits;
    }
    memory_guard.check();

    const SeedPlan plan =
        build_seed_plan(probe_len, max_mismatch, max_bulge, seed_len,
                        static_cast<int>(index.k()));
    const SequenceFetcher fetch =
        [&genome](const std::string& seqid, std::int64_t start,
                  std::int64_t end) {
            return genome.fetch(seqid, static_cast<std::uint64_t>(
                                           std::max<std::int64_t>(0, start)),
                                static_cast<std::uint64_t>(
                                    std::max<std::int64_t>(0, end)));
        };
    const std::string pam_value = pam.value_or("");

    if (!plan.guaranteed) {
        if (index.total_bases() > kMaxExhaustiveFallbackBases) {
            throw OfftargetError(
                ExitCode::unsupported, "UNSUPPORTED_SEARCH",
                "Unsupported indexed search configuration: " +
                    plan.reason +
                    ". Use the exact backend, a smaller index k, or "
                    "reduce max_bulge/max_mismatch.");
        }
        std::unordered_set<HitKey, HitKeyHash> seen_hits;
        std::uint64_t candidate_checks = 0;
        for (const ContigRecord& contig : index.contigs()) {
            const std::optional<std::string> maybe_sequence =
                genome.fetch_all(contig.name);
            if (!maybe_sequence.has_value()) {
                continue;
            }
            const std::string& sequence = *maybe_sequence;
            const std::int64_t sequence_len =
                static_cast<std::int64_t>(sequence.size());
            const std::int64_t range_end = std::max<std::int64_t>(
                0, sequence_len - probe_len + max_bulge + 1);
            for (std::int64_t candidate_start = 0;
                 candidate_start < range_end; ++candidate_start) {
                memory_guard.checkpoint(++candidate_checks);
                const std::int64_t window_start =
                    std::max<std::int64_t>(0,
                                           candidate_start - max_bulge);
                const std::int64_t window_end = std::min<std::int64_t>(
                    sequence_len, candidate_start + probe_len + max_bulge);
                if (window_end <= window_start) {
                    continue;
                }
                const std::string window = sequence.substr(
                    static_cast<std::size_t>(window_start),
                    static_cast<std::size_t>(window_end - window_start));
                const std::int64_t center =
                    candidate_start - window_start;
                const auto alignment = best_alignment(
                    window, probe, center, max_bulge, max_mismatch,
                    [&](std::int64_t local_start,
                        std::int64_t local_end) {
                        return pam_ok_span(
                            contig.name,
                            window_start + local_start,
                            window_start + local_end, target_strand,
                            pam_value, pam_side, fetch);
                    });
                if (!alignment.has_value() ||
                    alignment->mismatches > max_mismatch ||
                    alignment->indels() > max_bulge) {
                    continue;
                }
                Hit hit = alignment_to_hit(
                    *alignment, contig.name,
                    static_cast<std::uint64_t>(window_start),
                    target_strand);
                const HitKey key{hit.target, hit.target_start,
                                 hit.target_end,
                                 target_strand.empty()
                                     ? '+'
                                     : target_strand.front()};
                if (seen_hits.contains(key)) {
                    continue;
                }
                if (!pam_ok_span(contig.name, hit.target_start,
                                 hit.target_end, target_strand, pam_value,
                                 pam_side, fetch)) {
                    continue;
                }
                hit.pam = pam_sequence_span(
                    contig.name, hit.target_start, hit.target_end,
                    target_strand, pam_value, pam_side, fetch);
                seen_hits.insert(key);
                hits.push_back(std::move(hit));
            }
        }
        return hits;
    }

    std::unordered_set<CandidateKey, CandidateKeyHash> seen_candidates;
    std::unordered_set<HitKey, HitKeyHash> seen_hits;
    const int k = static_cast<int>(index.k());
    std::uint64_t candidate_checks = 0;
    for (const SeedSegment& segment : plan.segments) {
        const std::string seed = probe.substr(
            static_cast<std::size_t>(segment.start),
            static_cast<std::size_t>(segment.length));
        for (int offset = 0; offset <= static_cast<int>(seed.size()) - k;
             ++offset) {
            std::uint32_t seed_code = 0;
            if (!encode_kmer(seed.substr(static_cast<std::size_t>(offset),
                                         static_cast<std::size_t>(k)),
                             seed_code)) {
                continue;
            }
            for_each_seed_variant(
                seed_code, k, segment.allowed_mismatches,
                [&](std::uint32_t code) {
                    const std::span<const std::uint8_t> positions =
                        index.positions_bytes(code);
                    const std::size_t width = index.position_width();
                    const std::size_t count =
                        width == 0 ? 0 : positions.size() / width;
                    for (std::size_t position_index = 0;
                         position_index < count; ++position_index) {
                        memory_guard.checkpoint(++candidate_checks);
                        const std::uint64_t global_position =
                            decode_position(positions, position_index,
                                            width);
                        if (global_position <
                            static_cast<std::uint64_t>(
                                segment.start + offset)) {
                            continue;
                        }
                        const std::uint64_t candidate_global =
                            global_position -
                            static_cast<std::uint64_t>(
                                segment.start + offset);
                        std::string seqid;
                        std::uint64_t local_start = 0;
                        if (locate_or_none(index, candidate_global, seqid,
                                           local_start) == 0) {
                            continue;
                        }
                        const char strand =
                            target_strand.empty()
                                ? '+'
                                : target_strand.front();
                        const CandidateKey candidate_key{
                            seqid, local_start, strand};
                        if (!seen_candidates.insert(candidate_key).second) {
                            continue;
                        }
                        const std::uint64_t fetch_start =
                            local_start >
                                    static_cast<std::uint64_t>(
                                        kDefaultContext)
                                ? local_start - kDefaultContext
                                : 0;
                        const std::uint64_t fetch_end =
                            local_start +
                            static_cast<std::uint64_t>(probe_len) +
                            kDefaultContext;
                        const std::optional<std::string> maybe_window =
                            genome.fetch(seqid, fetch_start, fetch_end);
                        if (!maybe_window.has_value()) {
                            continue;
                        }
                        const std::string& window = *maybe_window;
                        const std::int64_t center =
                            static_cast<std::int64_t>(local_start -
                                                      fetch_start);
                        const auto alignment = best_alignment(
                            window, probe, center, max_bulge,
                            max_mismatch,
                            [&](std::int64_t local_alignment_start,
                                std::int64_t local_alignment_end) {
                                return pam_ok_span(
                                    seqid,
                                    static_cast<std::int64_t>(fetch_start) +
                                        local_alignment_start,
                                    static_cast<std::int64_t>(fetch_start) +
                                        local_alignment_end,
                                    target_strand, pam_value, pam_side,
                                    fetch);
                            });
                        if (!alignment.has_value() ||
                            alignment->mismatches > max_mismatch ||
                            alignment->indels() > max_bulge) {
                            continue;
                        }
                        Hit hit = alignment_to_hit(*alignment, seqid,
                                                   fetch_start,
                                                   target_strand);
                        const HitKey hit_key{
                            hit.target, hit.target_start, hit.target_end,
                            strand};
                        if (seen_hits.contains(hit_key)) {
                            continue;
                        }
                        if (!pam_ok_span(
                                seqid, hit.target_start, hit.target_end,
                                target_strand, pam_value, pam_side,
                                fetch)) {
                            continue;
                        }
                        hit.pam = pam_sequence_span(
                            seqid, hit.target_start, hit.target_end,
                            target_strand, pam_value, pam_side, fetch);
                        seen_hits.insert(hit_key);
                        hits.push_back(std::move(hit));
                    }
                    return true;
                });
        }
    }
    return hits;
}

struct GuideSearchWork {
    GuideRecord guide;
    std::vector<Hit> hits;
    std::uint64_t candidates = 0;
    bool plan_guaranteed = true;
    std::exception_ptr error;
};

GuideSearchWork search_one_guide(
    const GenomeIndex& index, GenomeSource& genome,
    const GuideRecord& guide, const SearchOptions& options,
    const std::optional<std::string>& pam_value,
    MemoryGuard& memory_guard) {
    GuideSearchWork work;
    work.guide = guide;
    if (guide.sequence.empty()) {
        return work;
    }
    memory_guard.check();

    const SeedPlan plan = build_seed_plan(
        static_cast<int>(guide.sequence.size()), options.max_mismatch,
        options.max_bulge, options.seed_len,
        static_cast<int>(index.k()));
    work.plan_guaranteed = plan.guaranteed;
    for (const auto& [probe, strand] :
         std::array<std::pair<std::string, std::string>, 2>{
             std::make_pair(guide.sequence, std::string("+")),
             std::make_pair(reverse_complement(guide.sequence),
                            std::string("-"))}) {
        std::vector<Hit> probe_hits = search_probe(
            index, genome, probe, strand, options.max_mismatch,
            options.max_bulge, options.seed_len, pam_value,
            options.pam_side, memory_guard);
        work.candidates += probe_hits.size();
        for (Hit& hit : probe_hits) {
            hit.qid = guide.qid;
            hit.guide = guide.sequence;
        }
        work.hits.insert(
            work.hits.end(),
            std::make_move_iterator(probe_hits.begin()),
            std::make_move_iterator(probe_hits.end()));
    }
    return work;
}

void deduplicate_and_sort(std::vector<Hit>& hits) {
    std::map<std::tuple<std::string, std::uint64_t, std::uint64_t, char>,
             std::size_t>
        unique;
    std::vector<Hit> deduplicated;
    deduplicated.reserve(hits.size());
    for (Hit& hit : hits) {
        const auto key = std::make_tuple(
            hit.target, hit.target_start, hit.target_end,
            hit.strand.empty() ? '+' : hit.strand.front());
        const auto iterator = unique.find(key);
        if (iterator == unique.end()) {
            unique[key] = deduplicated.size();
            deduplicated.push_back(std::move(hit));
            continue;
        }
        Hit& current = deduplicated[iterator->second];
        if (std::make_pair(hit.mismatch, hit.indel) <
            std::make_pair(current.mismatch, current.indel)) {
            current = std::move(hit);
        }
    }
    std::stable_sort(deduplicated.begin(), deduplicated.end(), hit_less);
    hits = std::move(deduplicated);
}

std::optional<double> parse_status_kb(const std::string& line) {
    if (line.find("VmRSS:") == 0 || line.find("VmHWM:") == 0) {
        std::istringstream input(line);
        std::string key;
        double value = 0.0;
        std::string unit;
        input >> key >> value >> unit;
        return value / 1024.0;
    }
    return std::nullopt;
}

}  // namespace

bool auto_sequence_cache_fits(
    std::uint64_t genome_bytes, std::uint64_t worker_count,
    std::uint64_t available_memory_mb) noexcept {
    if (genome_bytes == 0 || worker_count == 0) {
        return false;
    }
    const std::uint64_t genome_mb =
        genome_bytes / kMiB + (genome_bytes % kMiB == 0 ? 0 : 1);
    if (genome_mb >
        std::numeric_limits<std::uint64_t>::max() -
            kAutoCacheWorkerOverheadMb) {
        return false;
    }
    const std::uint64_t per_worker_mb =
        genome_mb + kAutoCacheWorkerOverheadMb;
    const std::uint64_t usable_mb =
        available_memory_mb > kAutoCacheReservedMemoryMb
            ? available_memory_mb - kAutoCacheReservedMemoryMb
            : 0;
    const std::uint64_t cache_budget_mb =
        usable_mb / kAutoCacheMemoryDivisor;
    return per_worker_mb <= cache_budget_mb / worker_count;
}

std::string hit_json(const Hit& hit) {
    std::ostringstream out;
    out << "{\"type\":\"hit\",\"qid\":" << json_quote(hit.qid)
        << ",\"guide\":" << json_quote(hit.guide)
        << ",\"target\":" << json_quote(hit.target)
        << ",\"start\":" << hit.start
        << ",\"strand\":" << json_quote(hit.strand)
        << ",\"mismatch\":" << hit.mismatch
        << ",\"indel\":" << hit.indel
        << ",\"rna_bulges\":" << hit.rna_bulges
        << ",\"dna_bulges\":" << hit.dna_bulges
        << ",\"pam\":" << json_quote(hit.pam)
        << ",\"bitscore\":" << std::fixed << std::setprecision(2)
        << hit.bitscore
        << ",\"target_start\":" << hit.target_start
        << ",\"target_end\":" << hit.target_end
        << ",\"query_start\":" << hit.query_start
        << ",\"query_end\":" << hit.query_end
        << ",\"cigar\":" << json_quote(hit.cigar)
        << ",\"aligned_guide\":" << json_quote(hit.aligned_guide)
        << ",\"aligned_target\":" << json_quote(hit.aligned_target)
        << ",\"engine\":" << json_quote(hit.engine) << '}';
    return out.str();
}

std::vector<GuideRecord> read_guides(
    const std::filesystem::path& path) {
    std::ifstream file;
    std::istream* input = nullptr;
    if (path == "-") {
        input = &std::cin;
    } else {
        file.open(path, std::ios::binary);
        if (!file) {
            throw OfftargetError(ExitCode::io, "MISSING_GUIDES",
                                 "Guide file not found: " + path.string());
        }
        input = &file;
    }

    std::string header_line;
    if (!std::getline(*input, header_line)) {
        throw OfftargetError(ExitCode::io, "EMPTY_GUIDES",
                             "Guide input is empty");
    }
    const std::vector<std::string> header =
        parse_tsv_line(strip_cr(header_line));
    std::optional<std::size_t> qid_column;
    std::optional<std::size_t> guide_column;
    for (std::size_t index = 0; index < header.size(); ++index) {
        if (header[index] == "qid" || header[index] == "id" ||
            header[index] == "seq_id") {
            if (!qid_column.has_value()) {
                qid_column = index;
            }
        }
        if (header[index] == "guide_seq" ||
            header[index] == "spacer_seq") {
            if (!guide_column.has_value()) {
                guide_column = index;
            }
        }
    }
    if (!guide_column.has_value()) {
        throw OfftargetError(
            ExitCode::io, "MISSING_GUIDE_COLUMN",
            "Guide TSV must contain a guide_seq column");
    }

    std::vector<GuideRecord> guides;
    std::string line;
    std::size_t ordinal = 0;
    while (std::getline(*input, line)) {
        line = strip_cr(std::move(line));
        if (line.empty()) {
            ++ordinal;
            continue;
        }
        const std::vector<std::string> fields = parse_tsv_line(line);
        GuideRecord guide;
        if (guide_column.value() >= fields.size()) {
            ++ordinal;
            continue;
        }
        guide.sequence = normalize_probe(fields[*guide_column]);
        if (qid_column.has_value() &&
            *qid_column < fields.size() && !fields[*qid_column].empty()) {
            guide.qid = fields[*qid_column];
        } else {
            guide.qid = "guide_" + std::to_string(ordinal);
        }
        guides.push_back(std::move(guide));
        ++ordinal;
    }
    return guides;
}

std::vector<GuideResult> search_indexed(const SearchOptions& options,
                                        SearchSummary& summary) {
    const auto start_time = std::chrono::steady_clock::now();
    const FastaFile genome(options.genome_path);
    genome.ensure_index_file();
    const GenomeIndex index = GenomeIndex::load(options.index_path);
    if (!index.is_valid_for(options.genome_path)) {
        throw OfftargetError(
            ExitCode::io, "STALE_INDEX",
            "index fingerprint does not match genome");
    }

    const std::vector<GuideRecord> guides =
        read_guides(options.guides_path);
    summary.guides = guides.size();
    summary.candidates = 0;
    summary.hits = 0;
    summary.exhaustive_seed_plan = true;

    const std::size_t requested_workers =
        static_cast<std::size_t>(std::max(1, options.threads));
    const std::size_t worker_count =
        guides.empty() ? 0 : std::min(requested_workers, guides.size());

    const std::uint64_t genome_bytes =
        std::filesystem::file_size(options.genome_path);
    const std::uint64_t estimate_workers =
        std::max<std::uint64_t>(1, static_cast<std::uint64_t>(worker_count));
    const auto estimate_peak = [&](bool use_cache) {
        return estimate_search_peak_mb(
            genome_bytes, index.index_bytes(), estimate_workers,
            guides.size(), use_cache);
    };

    bool use_sequence_cache = false;
    if (options.cache_genome == "true") {
        use_sequence_cache = true;
    } else if (options.cache_genome == "auto") {
        const auto available = available_memory_mb();
        if (available.has_value()) {
            use_sequence_cache = auto_sequence_cache_fits(
                genome_bytes, worker_count, *available);
        }
    }
    if (options.max_memory_mb > 0 && use_sequence_cache &&
        estimate_peak(true) > options.max_memory_mb &&
        options.cache_genome == "auto") {
        use_sequence_cache = false;
    }
    const std::uint64_t estimated_peak_mb =
        estimate_peak(use_sequence_cache);
    if (options.max_memory_mb > 0 &&
        estimated_peak_mb > options.max_memory_mb) {
        throw_memory_limit(
            options.max_memory_mb, estimated_peak_mb, "search startup");
    }
    summary.sequence_cache = use_sequence_cache;
    summary.memory_limit_mb = options.max_memory_mb;
    summary.estimated_peak_mb =
        static_cast<double>(estimated_peak_mb);

    const std::string pam =
        options.require_pam ? options.pam.value_or("") : "";
    const std::optional<std::string> pam_value =
        pam.empty() ? std::nullopt
                    : std::optional<std::string>(pam);

    int maximum_guide_len = 0;
    for (const GuideRecord& guide : guides) {
        maximum_guide_len =
            std::max(maximum_guide_len,
                     static_cast<int>(guide.sequence.size()));
    }

    std::vector<GuideSearchWork> guide_results(guides.size());
    for (std::size_t index_position = 0;
         index_position < guides.size(); ++index_position) {
        guide_results[index_position].guide = guides[index_position];
    }

    std::atomic<std::size_t> next_guide{0};
    std::atomic<bool> cancel{false};
    std::atomic<double> observed_peak_mb{peak_rss_mb()};
    MemoryGuard memory_guard(
        options.max_memory_mb, cancel, observed_peak_mb);
    std::mutex error_mutex;
    std::exception_ptr critical_error;
    const auto record_error = [&](std::exception_ptr error,
                                  bool memory_error) {
        std::lock_guard<std::mutex> lock(error_mutex);
        if (!critical_error) {
            critical_error = error;
        }
        if (memory_error) {
            cancel.store(true, std::memory_order_relaxed);
        }
    };
    auto worker = [&]() {
        try {
            const FastaFile worker_genome(options.genome_path);
            GenomeSource genome_source(worker_genome, use_sequence_cache);
            while (true) {
                memory_guard.check();
                if (cancel.load(std::memory_order_relaxed)) {
                    break;
                }
                const std::size_t index_position =
                    next_guide.fetch_add(1, std::memory_order_relaxed);
                if (index_position >= guides.size()) {
                    break;
                }
                GuideSearchWork& result = guide_results[index_position];
                try {
                    result = search_one_guide(
                        index, genome_source, guides[index_position],
                        options, pam_value, memory_guard);
                } catch (const OfftargetError& error) {
                    result.error = std::current_exception();
                    if (error.code() == ExitCode::memory_limit) {
                        record_error(result.error, true);
                    }
                } catch (...) {
                    result.error = std::current_exception();
                }
            }
        } catch (const OfftargetError& error) {
            record_error(
                std::current_exception(),
                error.code() == ExitCode::memory_limit);
        } catch (...) {
            record_error(std::current_exception(), false);
        }
    };

    std::vector<std::thread> workers;
    workers.reserve(worker_count);
    for (std::size_t worker_index = 0; worker_index < worker_count;
         ++worker_index) {
        workers.emplace_back(worker);
    }
    for (std::thread& thread : workers) {
        thread.join();
    }
    if (critical_error) {
        std::rethrow_exception(critical_error);
    }

    std::vector<GuideResult> results;
    std::unordered_map<std::string, std::size_t> result_by_qid;
    for (GuideSearchWork& work : guide_results) {
        if (work.error) {
            std::rethrow_exception(work.error);
        }
        summary.exhaustive_seed_plan =
            summary.exhaustive_seed_plan && work.plan_guaranteed;
        summary.candidates += work.candidates;
        if (options.max_candidates.has_value() &&
            summary.candidates > *options.max_candidates) {
            throw OfftargetError(
                ExitCode::unsupported, "CANDIDATE_GUARD",
                "Native search exceeded --max-candidates; no results "
                "were emitted");
        }
        if (work.guide.sequence.empty()) {
            continue;
        }

        const auto iterator = result_by_qid.find(work.guide.qid);
        std::size_t result_index = 0;
        if (iterator == result_by_qid.end()) {
            result_index = results.size();
            result_by_qid.emplace(work.guide.qid, result_index);
            results.push_back(GuideResult{work.guide, {}});
        } else {
            result_index = iterator->second;
        }
        GuideResult& result = results[result_index];
        result.hits.insert(
            result.hits.end(),
            std::make_move_iterator(work.hits.begin()),
            std::make_move_iterator(work.hits.end()));
    }

    for (GuideResult& result : results) {
        deduplicate_and_sort(result.hits);
        summary.hits += result.hits.size();
    }
    memory_guard.check();
    const SeedPlan summary_plan = build_seed_plan(
        maximum_guide_len, options.max_mismatch, options.max_bulge,
        options.seed_len, static_cast<int>(index.k()));
    summary.seed_plan_guaranteed = summary_plan.guaranteed;
    summary.exhaustive_seed_plan =
        summary.exhaustive_seed_plan && summary_plan.guaranteed;
    summary.search_time_s = std::chrono::duration<double>(
                                std::chrono::steady_clock::now() -
                                start_time)
                                .count();
    summary.memory_peak_mb = peak_rss_mb();
    summary.observed_peak_mb =
        std::max(observed_peak_mb.load(std::memory_order_relaxed),
                 summary.memory_peak_mb);
    summary.memory_peak_mb = summary.observed_peak_mb;
    return results;
}

void write_search_jsonl(std::ostream& out,
                        const std::vector<GuideResult>& results,
                        const SearchSummary& summary, std::uint32_t index_k,
                        int progress_every) {
    out << "{\"type\":\"meta\",\"schema_version\":1,"
           "\"engine\":\"indexed\","
           "\"implementation\":\"native-cpp\",\"index_k\":"
        << index_k << "}\n";
    std::uint64_t done = 0;
    for (const GuideResult& result : results) {
        for (const Hit& hit : result.hits) {
            out << hit_json(hit) << '\n';
        }
        ++done;
        if (progress_every > 0 &&
            (done % static_cast<std::uint64_t>(progress_every) == 0 ||
             done == summary.guides)) {
            out << "{\"type\":\"progress\",\"done\":" << done
                << ",\"total\":" << summary.guides
                << ",\"qid\":" << json_quote(result.guide.qid) << "}\n";
        }
    }
    out << "{\"type\":\"summary\",\"guides\":" << summary.guides
        << ",\"hits\":" << summary.hits
        << ",\"candidates\":" << summary.candidates
        << ",\"search_time_s\":" << std::fixed << std::setprecision(3)
        << summary.search_time_s
        << ",\"memory_peak_mb\":" << std::setprecision(2)
        << summary.memory_peak_mb
        << ",\"memory_limit_mb\":" << summary.memory_limit_mb
        << ",\"estimated_peak_mb\":" << std::setprecision(2)
        << summary.estimated_peak_mb
        << ",\"observed_peak_mb\":" << std::setprecision(2)
        << summary.observed_peak_mb
        << ",\"seed_plan_guaranteed\":"
        << (summary.seed_plan_guaranteed ? "true" : "false")
        << ",\"exhaustive_seed_plan\":"
        << (summary.exhaustive_seed_plan ? "true" : "false")
        << ",\"sequence_cache\":"
        << (summary.sequence_cache ? "true" : "false") << "}\n";
}

double current_rss_mb() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS_EX counters{};
    counters.cb = sizeof(counters);
    if (GetProcessMemoryInfo(
            GetCurrentProcess(),
            reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),
            sizeof(counters))) {
        return static_cast<double>(counters.WorkingSetSize) /
               (1024.0 * 1024.0);
    }
    return 0.0;
#else
    std::ifstream status("/proc/self/status");
    std::string line;
    while (std::getline(status, line)) {
        const auto value = parse_status_kb(line);
        if (value.has_value()) {
            return *value;
        }
    }
    return 0.0;
#endif
}

double peak_rss_mb() {
#ifdef _WIN32
    PROCESS_MEMORY_COUNTERS_EX counters{};
    counters.cb = sizeof(counters);
    if (GetProcessMemoryInfo(
            GetCurrentProcess(),
            reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),
            sizeof(counters))) {
        return static_cast<double>(counters.PeakWorkingSetSize) /
               (1024.0 * 1024.0);
    }
    return current_rss_mb();
#else
    std::ifstream status("/proc/self/status");
    std::string line;
    while (std::getline(status, line)) {
        if (line.find("VmHWM:") == 0) {
            const auto value = parse_status_kb(line);
            if (value.has_value()) {
                return *value;
            }
        }
    }
    return current_rss_mb();
#endif
}

namespace {

std::optional<std::uint64_t> available_memory_mb() {
#ifdef _WIN32
    MEMORYSTATUSEX status{};
    status.dwLength = sizeof(status);
    if (GlobalMemoryStatusEx(&status)) {
        return status.ullAvailPhys / (1024ULL * 1024ULL);
    }
    return std::nullopt;
#else
    std::ifstream input("/proc/meminfo");
    std::string line;
    while (std::getline(input, line)) {
        if (line.rfind("MemAvailable:", 0) == 0) {
            std::istringstream parser(line);
            std::string key;
            std::uint64_t value = 0;
            std::string unit;
            parser >> key >> value >> unit;
            return value / 1024;
        }
    }
    return std::nullopt;
#endif
}

}  // namespace

}  // namespace offtarget

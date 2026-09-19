#pragma once

#include "offtarget/fasta.hpp"
#include "offtarget/genome_index.hpp"
#include "offtarget/hit.hpp"

#include <cstdint>
#include <filesystem>
#include <functional>
#include <optional>
#include <ostream>
#include <string>
#include <vector>

namespace offtarget {

struct GuideRecord {
    std::string qid;
    std::string sequence;
};

struct SearchOptions {
    std::filesystem::path genome_path;
    std::filesystem::path index_path;
    std::filesystem::path guides_path;
    std::optional<std::filesystem::path> output_path;
    int max_mismatch = 4;
    int max_bulge = 0;
    int seed_len = 12;
    std::optional<int> seed_mismatch;
    std::optional<int> seed_mismatch_max;
    bool require_pam = false;
    std::optional<std::string> pam;
    std::string pam_side = "3prime";
    int threads = 1;
    std::string cache_genome = "auto";
    int progress_every = 1;
    std::optional<std::uint64_t> max_candidates;
    std::uint64_t max_memory_mb = 0;
};

struct SearchSummary {
    std::uint64_t guides = 0;
    std::uint64_t hits = 0;
    std::uint64_t candidates = 0;
    double search_time_s = 0.0;
    double memory_peak_mb = 0.0;
    std::uint64_t memory_limit_mb = 0;
    double estimated_peak_mb = 0.0;
    double observed_peak_mb = 0.0;
    bool seed_plan_guaranteed = false;
    bool exhaustive_seed_plan = false;
    bool sequence_cache = false;
};

struct GuideResult {
    GuideRecord guide;
    std::vector<Hit> hits;
};

[[nodiscard]] bool auto_sequence_cache_fits(
    std::uint64_t genome_bytes, std::uint64_t worker_count,
    std::uint64_t available_memory_mb) noexcept;

std::vector<GuideRecord> read_guides(
    const std::filesystem::path& path);
std::vector<GuideResult> search_indexed(const SearchOptions& options,
                                        SearchSummary& summary);
void write_search_jsonl(std::ostream& out,
                        const std::vector<GuideResult>& results,
                        const SearchSummary& summary, std::uint32_t index_k,
                        int progress_every);

double current_rss_mb();
double peak_rss_mb();

}  // namespace offtarget

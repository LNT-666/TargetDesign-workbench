#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>

namespace offtarget {

struct BuildOptions {
    std::filesystem::path genome_path;
    std::filesystem::path prefix;
    int k = 12;
    int threads = 1;
    std::optional<std::filesystem::path> contigs_path;
    bool force = false;
    std::optional<std::filesystem::path> output_path;
    std::uint64_t max_memory_mb = 0;
};

struct BuildSummary {
    int k = 0;
    std::uint64_t total_bases = 0;
    std::uint64_t valid_kmer_positions = 0;
    std::uint64_t contig_count = 0;
    std::string position_dtype;
    double build_time_s = 0.0;
    double memory_peak_mb = 0.0;
    std::uint64_t memory_limit_mb = 0;
    double estimated_peak_mb = 0.0;
    double observed_peak_mb = 0.0;
    std::uint64_t index_bytes = 0;
    std::string json;
};

BuildSummary build_index(const BuildOptions& options);

}  // namespace offtarget

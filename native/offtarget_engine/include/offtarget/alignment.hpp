#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <string>

namespace offtarget {

struct AlignmentRecord {
    std::int64_t target_start = 0;
    std::int64_t target_end = 0;
    std::int64_t query_start = 0;
    std::int64_t query_end = 0;
    int mismatches = 0;
    int rna_bulges = 0;
    int dna_bulges = 0;
    std::string cigar;
    std::string query_aligned;
    std::string target_aligned;

    [[nodiscard]] int indels() const noexcept {
        return rna_bulges + dna_bulges;
    }
    [[nodiscard]] int edit_cost() const noexcept {
        return mismatches * 2 + indels() * 3;
    }
};

std::string reverse_complement_gapped(const std::string& sequence);
std::string reverse_complement(const std::string& sequence);
std::string cigar_from_operations(const std::string& operations);
AlignmentRecord align_global(std::string query, std::string target);

using AcceptAlignment =
    std::function<bool(std::int64_t target_start, std::int64_t target_end)>;

std::optional<AlignmentRecord> best_alignment(
    std::string window, std::string query, std::int64_t center,
    int max_bulge, std::optional<int> max_mismatch = std::nullopt,
    const AcceptAlignment& accept_alignment = {});

}  // namespace offtarget

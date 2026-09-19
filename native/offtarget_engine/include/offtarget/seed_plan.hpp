#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace offtarget {

constexpr std::uint64_t kDefaultMaxSeedVariants = 500000;

struct SeedSegment {
    int start = 0;
    int length = 0;
    int allowed_mismatches = 0;

    [[nodiscard]] int end() const noexcept { return start + length; }
};

struct SeedPlan {
    std::vector<SeedSegment> segments;
    bool guaranteed = false;
    std::string reason;
    std::uint64_t estimated_variants = 0;
};

std::uint64_t variant_count(int seed_len, int max_mismatch);
SeedPlan build_seed_plan(int probe_len, int max_mismatch, int max_bulge,
                         int seed_len, int kmer_size,
                         std::uint64_t max_variants =
                             kDefaultMaxSeedVariants);
bool encode_kmer(const std::string& kmer, std::uint32_t& code);
void for_each_seed_variant(
    std::uint32_t seed_code, int k, int max_mismatch,
    const std::function<bool(std::uint32_t)>& callback);

}  // namespace offtarget

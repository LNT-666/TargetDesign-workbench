#include "offtarget/seed_plan.hpp"

#include "offtarget/fasta.hpp"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <tuple>

namespace offtarget {

namespace {

std::uint64_t capped_add(std::uint64_t left, std::uint64_t right,
                         std::uint64_t cap) {
    if (left > cap || right > cap || left > cap - right) {
        return cap + 1;
    }
    return left + right;
}

std::uint64_t capped_mul(std::uint64_t left, std::uint64_t right,
                         std::uint64_t cap) {
    if (left == 0 || right == 0) {
        return 0;
    }
    if (left > cap / right) {
        return cap + 1;
    }
    return left * right;
}

std::uint64_t binomial(std::uint64_t n, std::uint64_t k,
                       std::uint64_t cap) {
    if (k > n) {
        return 0;
    }
    k = std::min(k, n - k);
    std::uint64_t result = 1;
    for (std::uint64_t index = 1; index <= k; ++index) {
        result = capped_mul(result, n - k + index, cap) / index;
    }
    return result;
}

std::uint64_t power_three(std::uint64_t exponent, std::uint64_t cap) {
    std::uint64_t result = 1;
    for (std::uint64_t index = 0; index < exponent; ++index) {
        result = capped_mul(result, 3, cap);
    }
    return result;
}

std::vector<int> partition_lengths(int length, int count) {
    std::vector<int> sizes(static_cast<std::size_t>(count), length / count);
    const int remainder = length % count;
    for (int index = 0; index < remainder; ++index) {
        ++sizes[static_cast<std::size_t>(index)];
    }
    return sizes;
}

std::uint64_t segmented_variant_work(int segment_len, int kmer_size,
                                     int max_mismatch) {
    const std::int64_t window_count =
        std::max<std::int64_t>(1, segment_len - kmer_size + 1);
    const std::uint64_t variants = variant_count(kmer_size, max_mismatch);
    return static_cast<std::uint64_t>(window_count) * variants;
}

void visit_variants(std::uint32_t code, int position, int k,
                    int remaining, std::uint32_t original,
                    const std::function<bool(std::uint32_t)>& callback,
                    bool& keep_going) {
    if (!keep_going) {
        return;
    }
    if (position == k) {
        keep_going = callback(code);
        return;
    }
    visit_variants(code, position + 1, k, remaining, original, callback,
                   keep_going);
    if (!keep_going || remaining == 0) {
        return;
    }
    const int shift = 2 * (k - 1 - position);
    const std::uint32_t old_base = (original >> shift) & 3U;
    for (std::uint32_t base = 0; base < 4; ++base) {
        if (base == old_base) {
            continue;
        }
        const std::uint32_t next =
            (code & ~(3U << shift)) | (base << shift);
        visit_variants(next, position + 1, k, remaining - 1, original,
                       callback, keep_going);
        if (!keep_going) {
            return;
        }
    }
}

}  // namespace

std::uint64_t variant_count(int seed_len, int max_mismatch) {
    seed_len = std::max(0, seed_len);
    max_mismatch = std::max(0, std::min(max_mismatch, seed_len));
    const std::uint64_t cap =
        std::numeric_limits<std::uint64_t>::max();
    std::uint64_t count = 0;
    for (int changes = 0; changes <= max_mismatch; ++changes) {
        const std::uint64_t combinations =
            binomial(static_cast<std::uint64_t>(seed_len),
                     static_cast<std::uint64_t>(changes), cap);
        const std::uint64_t substitutions =
            power_three(static_cast<std::uint64_t>(changes), cap);
        count = capped_add(count, capped_mul(combinations, substitutions, cap),
                           cap);
    }
    return count;
}

SeedPlan build_seed_plan(int probe_len, int max_mismatch, int max_bulge,
                         int seed_len, int kmer_size,
                         std::uint64_t max_variants) {
    (void)seed_len;
    probe_len = std::max(0, probe_len);
    max_mismatch = std::max(0, max_mismatch);
    max_bulge = std::max(0, max_bulge);
    const int minimum_seed_len = std::max(1, kmer_size);
    const int max_seed_count = probe_len / minimum_seed_len;
    const int minimum_seed_count = std::max(1, max_bulge + 1);

    if (max_seed_count < minimum_seed_count) {
        SeedPlan plan;
        plan.segments = {SeedSegment{0, probe_len, max_mismatch}};
        plan.reason =
            "need at least " + std::to_string(minimum_seed_count) +
            " non-overlapping " + std::to_string(minimum_seed_len) +
            "-nt seeds to cover max_bulge=" + std::to_string(max_bulge) +
            ", but the guide only fits " + std::to_string(max_seed_count);
        return plan;
    }

    bool found = false;
    std::uint64_t best_variants = 0;
    int best_count = 0;
    std::vector<SeedSegment> best_segments;
    for (int seed_count = minimum_seed_count;
         seed_count <= max_seed_count; ++seed_count) {
        const int denominator = seed_count - max_bulge;
        if (denominator <= 0) {
            continue;
        }
        const int allowed = max_mismatch / denominator;
        const std::vector<int> sizes =
            partition_lengths(probe_len, seed_count);
        std::uint64_t total_variants = 0;
        bool over_cap = false;
        for (const int size : sizes) {
            total_variants = capped_add(
                total_variants,
                segmented_variant_work(size, minimum_seed_len, allowed),
                max_variants);
            if (max_variants != 0 && total_variants > max_variants) {
                over_cap = true;
                break;
            }
        }
        if (over_cap) {
            continue;
        }

        std::vector<SeedSegment> segments;
        int cursor = 0;
        for (const int size : sizes) {
            segments.push_back(SeedSegment{cursor, size, allowed});
            cursor += size;
        }
        const auto key = std::make_tuple(total_variants, seed_count);
        if (!found ||
            key < std::make_tuple(best_variants, best_count)) {
            found = true;
            best_variants = total_variants;
            best_count = seed_count;
            best_segments = std::move(segments);
        }
    }

    if (!found) {
        SeedPlan plan;
        plan.segments = {SeedSegment{0, probe_len, max_mismatch}};
        plan.reason =
            "the exhaustive seed variants for max_mismatch=" +
            std::to_string(max_mismatch) +
            ", max_bulge=" + std::to_string(max_bulge) +
            " exceed the configured cap " + std::to_string(max_variants);
        return plan;
    }

    SeedPlan plan;
    plan.segments = std::move(best_segments);
    plan.guaranteed = true;
    plan.estimated_variants = best_variants;
    return plan;
}

bool encode_kmer(const std::string& kmer, std::uint32_t& code) {
    code = 0;
    for (const char raw : kmer) {
        std::uint32_t base = 0;
        switch (raw) {
            case 'A':
            case 'a':
                base = 0;
                break;
            case 'C':
            case 'c':
                base = 1;
                break;
            case 'G':
            case 'g':
                base = 2;
                break;
            case 'T':
            case 't':
            case 'U':
            case 'u':
                base = 3;
                break;
            default:
                return false;
        }
        code = (code << 2U) | base;
    }
    return true;
}

void for_each_seed_variant(
    std::uint32_t seed_code, int k, int max_mismatch,
    const std::function<bool(std::uint32_t)>& callback) {
    max_mismatch = std::max(0, std::min(max_mismatch, k));
    bool keep_going = true;
    visit_variants(seed_code, 0, k, max_mismatch, seed_code, callback,
                   keep_going);
}

}  // namespace offtarget

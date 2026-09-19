#pragma once

#include <cstdint>
#include <string>

namespace offtarget {

struct Hit {
    std::string qid;
    std::string guide;
    std::string target;
    std::uint64_t start = 0;
    std::string strand;
    int mismatch = 0;
    int indel = 0;
    int rna_bulges = 0;
    int dna_bulges = 0;
    std::string pam;
    double bitscore = 0.0;
    std::uint64_t target_start = 0;
    std::uint64_t target_end = 0;
    int query_start = 0;
    int query_end = 0;
    std::string cigar;
    std::string aligned_guide;
    std::string aligned_target;
    std::string engine = "indexed";
};

std::string hit_json(const Hit& hit);

}  // namespace offtarget

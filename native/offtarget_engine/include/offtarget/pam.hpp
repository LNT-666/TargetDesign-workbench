#pragma once

#include <cstdint>
#include <functional>
#include <optional>
#include <string>

namespace offtarget {

using SequenceFetcher =
    std::function<std::optional<std::string>(const std::string&, std::int64_t,
                                             std::int64_t)>;

bool iupac_match(const std::string& pattern, const std::string& sequence);
bool pam_ok_span(const std::string& seqid, std::int64_t target_start,
                 std::int64_t target_end, const std::string& strand,
                 const std::string& pam, const std::string& pam_side,
                 const SequenceFetcher& fetch);
std::string pam_sequence_span(
    const std::string& seqid, std::int64_t target_start,
    std::int64_t target_end, const std::string& strand,
    const std::string& pam, const std::string& pam_side,
    const SequenceFetcher& fetch);

}  // namespace offtarget

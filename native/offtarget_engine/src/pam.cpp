#include "offtarget/pam.hpp"

#include "offtarget/alignment.hpp"
#include "offtarget/fasta.hpp"

#include <array>
#include <cctype>

namespace offtarget {

namespace {

std::uint8_t base_bit(const char raw) {
    switch (static_cast<char>(
        std::toupper(static_cast<unsigned char>(raw)))) {
        case 'A':
            return 1U << 0U;
        case 'C':
            return 1U << 1U;
        case 'G':
            return 1U << 2U;
        case 'T':
        case 'U':
            return 1U << 3U;
        default:
            return 0;
    }
}

std::uint8_t iupac_mask(const char raw) {
    switch (static_cast<char>(
        std::toupper(static_cast<unsigned char>(raw)))) {
        case 'A':
            return 0x1;
        case 'C':
            return 0x2;
        case 'G':
            return 0x4;
        case 'T':
        case 'U':
            return 0x8;
        case 'R':
            return 0x1 | 0x4;
        case 'Y':
            return 0x2 | 0x8;
        case 'S':
            return 0x2 | 0x4;
        case 'W':
            return 0x1 | 0x8;
        case 'K':
            return 0x4 | 0x8;
        case 'M':
            return 0x1 | 0x2;
        case 'D':
            return 0x1 | 0x4 | 0x8;
        case 'H':
            return 0x1 | 0x2 | 0x8;
        case 'V':
            return 0x1 | 0x2 | 0x4;
        case 'B':
            return 0x2 | 0x4 | 0x8;
        case 'N':
            return 0xF;
        default:
            return 0;
    }
}

}  // namespace

bool iupac_match(const std::string& pattern, const std::string& sequence) {
    if (pattern.size() != sequence.size()) {
        return false;
    }
    for (std::size_t index = 0; index < pattern.size(); ++index) {
        const std::uint8_t mask = iupac_mask(pattern[index]);
        const std::uint8_t base = base_bit(sequence[index]);
        if (mask == 0 || base == 0 || (mask & base) == 0) {
            return false;
        }
    }
    return true;
}

bool pam_ok_span(const std::string& seqid, std::int64_t target_start,
                 std::int64_t target_end, const std::string& strand,
                 const std::string& pam, const std::string& pam_side,
                 const SequenceFetcher& fetch) {
    if (pam.empty()) {
        return true;
    }
    const std::int64_t pam_len =
        static_cast<std::int64_t>(pam.size());
    if (strand == "+") {
        const auto sequence =
            pam_side == "5prime"
                ? fetch(seqid, target_start - pam_len, target_start)
                : fetch(seqid, target_end, target_end + pam_len);
        return sequence.has_value() &&
               iupac_match(pam, uppercase_ascii(*sequence));
    }

    const std::string rc_pam = reverse_complement(pam);
    const auto sequence =
        pam_side == "5prime"
            ? fetch(seqid, target_end, target_end + pam_len)
            : fetch(seqid, target_start - pam_len, target_start);
    return sequence.has_value() &&
           iupac_match(rc_pam, uppercase_ascii(*sequence));
}

std::string pam_sequence_span(
    const std::string& seqid, std::int64_t target_start,
    std::int64_t target_end, const std::string& strand,
    const std::string& pam, const std::string& pam_side,
    const SequenceFetcher& fetch) {
    if (pam.empty()) {
        return {};
    }
    const std::int64_t pam_len =
        static_cast<std::int64_t>(pam.size());
    std::int64_t start = 0;
    std::int64_t end = 0;
    if (strand == "+") {
        if (pam_side == "5prime") {
            start = target_start - pam_len;
            end = target_start;
        } else {
            start = target_end;
            end = target_end + pam_len;
        }
    } else if (pam_side == "5prime") {
        start = target_end;
        end = target_end + pam_len;
    } else {
        start = target_start - pam_len;
        end = target_start;
    }
    std::optional<std::string> sequence = fetch(seqid, start, end);
    std::string value =
        sequence.has_value() ? uppercase_ascii(*sequence) : std::string{};
    if (strand == "-") {
        value = reverse_complement(value);
    }
    return value;
}

}  // namespace offtarget

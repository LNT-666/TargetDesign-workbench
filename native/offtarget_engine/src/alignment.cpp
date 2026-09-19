#include "offtarget/alignment.hpp"

#include "offtarget/fasta.hpp"

#include <algorithm>
#include <cstdlib>
#include <cstdint>
#include <limits>
#include <string>
#include <string_view>
#include <tuple>
#include <vector>

namespace offtarget {

namespace {

struct Score {
    int cost = 0;
    int gaps = 0;
    int mismatches = 0;
};

struct AlignmentWorkspace {
    std::vector<Score> scores;
    std::vector<char> back;
    std::vector<char> operations;
    std::vector<char> query_aligned;
    std::vector<char> target_aligned;
};

bool score_less(const Score& left, const Score& right) {
    return std::tie(left.cost, left.gaps, left.mismatches) <
           std::tie(right.cost, right.gaps, right.mismatches);
}

AlignmentWorkspace& thread_alignment_workspace() {
    thread_local AlignmentWorkspace workspace;
    return workspace;
}

Score align_global_scores(std::string_view query, std::string_view target,
                          AlignmentWorkspace& workspace) {
    const std::size_t query_len = query.size();
    const std::size_t target_len = target.size();
    const std::size_t columns = target_len + 1;
    const Score initial{};
    workspace.scores.assign((query_len + 1) * columns, initial);
    workspace.back.assign((query_len + 1) * columns, '\0');

    auto score_at = [&](std::size_t row, std::size_t column) -> Score& {
        return workspace.scores[row * columns + column];
    };
    auto back_at = [&](std::size_t row, std::size_t column) -> char& {
        return workspace.back[row * columns + column];
    };

    score_at(0, 0) = Score{0, 0, 0};
    for (std::size_t column = 1; column <= target_len; ++column) {
        score_at(0, column) =
            Score{3 * static_cast<int>(column),
                  static_cast<int>(column), 0};
        back_at(0, column) = 'D';
    }
    for (std::size_t row = 1; row <= query_len; ++row) {
        score_at(row, 0) =
            Score{3 * static_cast<int>(row), static_cast<int>(row), 0};
        back_at(row, 0) = 'I';
    }

    for (std::size_t row = 1; row <= query_len; ++row) {
        const char query_base = query[row - 1];
        for (std::size_t column = 1; column <= target_len; ++column) {
            const char target_base = target[column - 1];
            const int mismatch = query_base != target_base ? 1 : 0;

            const Score& diagonal = score_at(row - 1, column - 1);
            const Score diag_value{
                diagonal.cost + 2 * mismatch,
                diagonal.gaps,
                diagonal.mismatches + mismatch,
            };
            const Score& up = score_at(row - 1, column);
            const Score up_value{up.cost + 3, up.gaps + 1,
                                 up.mismatches};
            const Score& left = score_at(row, column - 1);
            const Score left_value{left.cost + 3, left.gaps + 1,
                                   left.mismatches};

            Score best = diag_value;
            char operation = mismatch == 0 ? 'M' : 'X';
            if (score_less(up_value, best)) {
                best = up_value;
                operation = 'I';
            }
            if (score_less(left_value, best)) {
                best = left_value;
                operation = 'D';
            }
            score_at(row, column) = best;
            back_at(row, column) = operation;
        }
    }
    return score_at(query_len, target_len);
}

AlignmentRecord materialize_alignment(std::string_view query,
                                      std::string_view target,
                                      const Score& terminal,
                                      AlignmentWorkspace& workspace) {
    const std::size_t query_len = query.size();
    const std::size_t target_len = target.size();
    const std::size_t columns = target_len + 1;
    const std::size_t alignment_length =
        std::max(query_len, target_len);

    workspace.operations.clear();
    workspace.query_aligned.clear();
    workspace.target_aligned.clear();
    workspace.operations.reserve(alignment_length);
    workspace.query_aligned.reserve(alignment_length);
    workspace.target_aligned.reserve(alignment_length);

    std::size_t row = query_len;
    std::size_t column = target_len;
    while (row > 0 || column > 0) {
        const char operation = workspace.back[row * columns + column];
        if (operation == 'M' || operation == 'X') {
            workspace.query_aligned.push_back(query[row - 1]);
            workspace.target_aligned.push_back(target[column - 1]);
            --row;
            --column;
        } else if (operation == 'I') {
            workspace.query_aligned.push_back(query[row - 1]);
            workspace.target_aligned.push_back('-');
            --row;
        } else if (operation == 'D') {
            workspace.query_aligned.push_back('-');
            workspace.target_aligned.push_back(target[column - 1]);
            --column;
        } else {
            throw std::runtime_error("alignment traceback is incomplete");
        }
        workspace.operations.push_back(operation);
    }
    std::reverse(workspace.operations.begin(), workspace.operations.end());
    std::reverse(workspace.query_aligned.begin(),
                 workspace.query_aligned.end());
    std::reverse(workspace.target_aligned.begin(),
                 workspace.target_aligned.end());

    AlignmentRecord result;
    result.target_start = 0;
    result.target_end = static_cast<std::int64_t>(target_len);
    result.query_start = 0;
    result.query_end = static_cast<std::int64_t>(query_len);
    result.mismatches = terminal.mismatches;
    result.rna_bulges = static_cast<int>(
        std::count(workspace.operations.begin(), workspace.operations.end(),
                   'I'));
    result.dna_bulges = static_cast<int>(
        std::count(workspace.operations.begin(), workspace.operations.end(),
                   'D'));
    result.cigar = cigar_from_operations(std::string(
        workspace.operations.begin(), workspace.operations.end()));
    result.query_aligned =
        std::string(workspace.query_aligned.begin(),
                    workspace.query_aligned.end());
    result.target_aligned =
        std::string(workspace.target_aligned.begin(),
                    workspace.target_aligned.end());
    return result;
}

char complement_base(const char raw) {
    switch (static_cast<char>(
        std::toupper(static_cast<unsigned char>(raw)))) {
        case 'A':
            return 'T';
        case 'C':
            return 'G';
        case 'G':
            return 'C';
        case 'T':
            return 'A';
        case 'U':
            return 'A';
        case 'N':
            return 'N';
        case '-':
            return '-';
        default:
            return raw;
    }
}

}  // namespace

std::string reverse_complement(const std::string& sequence) {
    std::string result;
    result.reserve(sequence.size());
    for (auto iterator = sequence.rbegin(); iterator != sequence.rend();
         ++iterator) {
        result.push_back(complement_base(*iterator));
    }
    return result;
}

std::string reverse_complement_gapped(const std::string& sequence) {
    return reverse_complement(sequence);
}

std::string cigar_from_operations(const std::string& operations) {
    if (operations.empty()) {
        return {};
    }
    std::string result;
    char current = operations.front();
    std::size_t count = 1;
    for (std::size_t index = 1; index < operations.size(); ++index) {
        if (operations[index] == current) {
            ++count;
            continue;
        }
        result += std::to_string(count);
        result.push_back(current);
        current = operations[index];
        count = 1;
    }
    result += std::to_string(count);
    result.push_back(current);
    return result;
}

AlignmentRecord align_global(std::string query, std::string target) {
    query = uppercase_ascii(std::move(query));
    target = uppercase_ascii(std::move(target));
    for (char& ch : query) {
        if (ch == 'U') {
            ch = 'T';
        }
    }
    for (char& ch : target) {
        if (ch == 'U') {
            ch = 'T';
        }
    }

    AlignmentWorkspace workspace;
    const Score terminal =
        align_global_scores(query, target, workspace);
    return materialize_alignment(query, target, terminal, workspace);
}

std::optional<AlignmentRecord> best_alignment(
    std::string window, std::string query, std::int64_t center,
    int max_bulge, std::optional<int> max_mismatch,
    const AcceptAlignment& accept_alignment) {
    window = uppercase_ascii(std::move(window));
    query = uppercase_ascii(std::move(query));
    for (char& ch : window) {
        if (ch == 'U') {
            ch = 'T';
        }
    }
    for (char& ch : query) {
        if (ch == 'U') {
            ch = 'T';
        }
    }

    const std::int64_t query_len =
        static_cast<std::int64_t>(query.size());
    const std::int64_t window_len =
        static_cast<std::int64_t>(window.size());
    if (query_len == 0 || window_len == 0) {
        return std::nullopt;
    }
    center = std::max<std::int64_t>(
        0, std::min(center, std::max<std::int64_t>(0, window_len - query_len)));
    max_bulge = std::max(0, max_bulge);
    const std::int64_t min_len =
        std::max<std::int64_t>(1, query_len - max_bulge);
    const std::int64_t max_len =
        std::min(window_len, query_len + max_bulge);
    const std::int64_t start_lo =
        std::max<std::int64_t>(0, center - max_bulge);
    const std::int64_t start_hi =
        std::min(window_len, center + max_bulge);

    if (max_bulge == 0) {
        if (center + query_len > window_len) {
            return std::nullopt;
        }
        const std::string target = window.substr(
            static_cast<std::size_t>(center),
            static_cast<std::size_t>(query_len));
        AlignmentRecord alignment;
        alignment.target_start = center;
        alignment.target_end = center + query_len;
        alignment.query_start = 0;
        alignment.query_end = query_len;
        alignment.query_aligned = query;
        alignment.target_aligned = target;
        std::string operations;
        operations.reserve(static_cast<std::size_t>(query_len));
        for (std::int64_t index = 0; index < query_len; ++index) {
            const bool mismatch =
                query[static_cast<std::size_t>(index)] !=
                target[static_cast<std::size_t>(index)];
            operations.push_back(mismatch ? 'X' : 'M');
            alignment.mismatches += mismatch ? 1 : 0;
        }
        if (max_mismatch.has_value() &&
            alignment.mismatches > *max_mismatch) {
            return std::nullopt;
        }
        if (accept_alignment &&
            !accept_alignment(alignment.target_start,
                              alignment.target_end)) {
            return std::nullopt;
        }
        alignment.cigar = cigar_from_operations(operations);
        return alignment;
    }

    std::optional<AlignmentRecord> best;
    std::optional<std::tuple<int, int, int, std::int64_t, std::int64_t,
                             std::int64_t, std::int64_t>>
        best_key;
    AlignmentWorkspace& workspace = thread_alignment_workspace();
    for (std::int64_t target_start = start_lo;
         target_start <= start_hi; ++target_start) {
        const std::int64_t end_limit = std::min(
            window_len, target_start + max_len);
        for (std::int64_t target_end = target_start + min_len;
             target_end <= end_limit; ++target_end) {
            if (target_end <= target_start) {
                continue;
            }
            const std::string_view target(
                window.data() + static_cast<std::size_t>(target_start),
                static_cast<std::size_t>(target_end - target_start));
            const Score terminal =
                align_global_scores(query, target, workspace);
            if (terminal.gaps > max_bulge) {
                continue;
            }
            if (max_mismatch.has_value() &&
                terminal.mismatches > *max_mismatch) {
                continue;
            }
            if (accept_alignment &&
                !accept_alignment(target_start, target_end)) {
                continue;
            }
            const auto key = std::make_tuple(
                terminal.cost, terminal.mismatches, terminal.gaps,
                static_cast<std::int64_t>(std::llabs(
                    static_cast<long long>(target_end - target_start) -
                    static_cast<long long>(query_len))),
                static_cast<std::int64_t>(std::llabs(
                    static_cast<long long>(target_start - center))),
                target_start, target_end);
            if (!best_key.has_value() || key < *best_key) {
                best_key = key;
                AlignmentRecord alignment = materialize_alignment(
                    query, target, terminal, workspace);
                alignment.target_start = target_start;
                alignment.target_end = target_end;
                alignment.query_start = 0;
                alignment.query_end = query_len;
                best = std::move(alignment);
            }
        }
    }
    return best;
}

}  // namespace offtarget

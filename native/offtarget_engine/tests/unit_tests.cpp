#include "offtarget/alignment.hpp"
#include "offtarget/build_index.hpp"
#include "offtarget/error.hpp"
#include "offtarget/json_writer.hpp"
#include "offtarget/pam.hpp"
#include "offtarget/search.hpp"
#include "offtarget/seed_plan.hpp"

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

class TempDirectory {
public:
    TempDirectory() {
        const auto stamp =
            std::chrono::steady_clock::now().time_since_epoch().count();
        path_ = std::filesystem::temp_directory_path() /
                ("offtarget-engine-test-" + std::to_string(stamp));
        std::filesystem::create_directories(path_);
    }

    ~TempDirectory() {
        std::error_code error;
        std::filesystem::remove_all(path_, error);
    }

    TempDirectory(const TempDirectory&) = delete;
    TempDirectory& operator=(const TempDirectory&) = delete;

    [[nodiscard]] const std::filesystem::path& path() const noexcept {
        return path_;
    }

private:
    std::filesystem::path path_;
};

void write_text(const std::filesystem::path& path,
                const std::string& text) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("cannot write test fixture: " +
                                 path.string());
    }
    output << text;
}

struct ParallelFixture {
    std::filesystem::path fasta;
    std::filesystem::path prefix;
    std::filesystem::path guides;
};

ParallelFixture write_parallel_fixture(
    const std::filesystem::path& directory) {
    const std::vector<std::string> guides = {
        "GCCTCTTTCCCACCCACCTT",
        "ACGTTGCAAGTCCTAGGATC",
        "AAAACCCCGGGGTTTTAAAA",
        "GATTACAGTTACCAGATTAC",
    };

    std::string fasta_text;
    for (std::size_t index = 0; index < guides.size(); ++index) {
        const std::string& guide = guides[index];
        fasta_text += ">forward" + std::to_string(index) + "\n";
        fasta_text += "T" + guide + "AGG" + "C" +
                      std::string(std::size_t{12}, 'A') + "\n";

        const std::string reverse_target =
            offtarget::reverse_complement(guide + "AGG");
        fasta_text += ">reverse" + std::to_string(index) + "\n";
        fasta_text += "G" + reverse_target + "A" +
                      std::string(std::size_t{12}, 'T') + "\n";
    }
    fasta_text += ">repeat2\n";
    fasta_text += "C" + guides[2] + "AGG" + guides[2] + "AGG" + "G" +
                  std::string(std::size_t{12}, 'A') + "\n";
    fasta_text += ">bulge3\n";
    fasta_text += "A" + guides[3].substr(0, 10) + "A" +
                  guides[3].substr(10) + "TGG" + "C" +
                  std::string(std::size_t{12}, 'A') + "\n";

    std::string guides_text = "qid\tguide_seq\n";
    for (std::size_t index = 0; index < guides.size(); ++index) {
        guides_text += "g" + std::to_string(index) + "\t" + guides[index] +
                       "\n";
    }

    ParallelFixture fixture;
    fixture.fasta = directory / "parallel.fa";
    fixture.prefix = directory / "parallel_index";
    fixture.guides = directory / "parallel.tsv";
    write_text(fixture.fasta, fasta_text);
    write_text(fixture.guides, guides_text);
    return fixture;
}

void check_results_equal(
    const std::vector<offtarget::GuideResult>& expected,
    const std::vector<offtarget::GuideResult>& observed,
    const std::string& context) {
    check(expected.size() == observed.size(),
          context + ": result count mismatch");
    for (std::size_t result_index = 0; result_index < expected.size();
         ++result_index) {
        const offtarget::GuideResult& expected_result =
            expected[result_index];
        const offtarget::GuideResult& observed_result =
            observed[result_index];
        check(expected_result.guide.qid == observed_result.guide.qid,
              context + ": qid order mismatch");
        check(expected_result.guide.sequence ==
                  observed_result.guide.sequence,
              context + ": guide order mismatch");
        check(expected_result.hits.size() == observed_result.hits.size(),
              context + ": hit count mismatch for " +
                  expected_result.guide.qid);
        for (std::size_t hit_index = 0;
             hit_index < expected_result.hits.size(); ++hit_index) {
            check(offtarget::hit_json(
                      expected_result.hits[hit_index]) ==
                      offtarget::hit_json(
                          observed_result.hits[hit_index]),
                  context + ": hit mismatch");
        }
    }
}

void test_parallel_search_determinism() {
    TempDirectory temporary;
    const ParallelFixture fixture =
        write_parallel_fixture(temporary.path());

    offtarget::BuildOptions build_options;
    build_options.genome_path = fixture.fasta;
    build_options.prefix = fixture.prefix;
    build_options.k = 10;
    build_options.threads = 2;
    offtarget::build_index(build_options);

    const auto run_search = [&](int threads, int max_bulge,
                                bool require_pam,
                                const std::string& cache_genome) {
        offtarget::SearchOptions options;
        options.genome_path = fixture.fasta;
        options.index_path = fixture.prefix;
        options.guides_path = fixture.guides;
        options.max_mismatch = 2;
        options.max_bulge = max_bulge;
        options.seed_len = 10;
        options.require_pam = require_pam;
        options.pam = "NGG";
        options.pam_side = "3prime";
        options.threads = threads;
        options.cache_genome = cache_genome;
        offtarget::SearchSummary summary;
        std::vector<offtarget::GuideResult> results =
            offtarget::search_indexed(options, summary);
        return std::make_pair(std::move(results), summary);
    };

    std::set<std::tuple<std::string, std::uint64_t, std::uint64_t,
                        std::string>>
        seen_hits;
    bool saw_plus = false;
    bool saw_minus = false;
    bool saw_repeat = false;
    for (const int max_bulge : {0, 1}) {
        for (const bool require_pam : {false, true}) {
            for (const std::string cache_genome : {"false", "true"}) {
                const auto expected =
                    run_search(1, max_bulge, require_pam, cache_genome);
                for (const int threads : {2, 4}) {
                    const auto observed = run_search(
                        threads, max_bulge, require_pam, cache_genome);
                    const std::string context =
                        "threads=" + std::to_string(threads) +
                        " bulge=" + std::to_string(max_bulge) +
                        " pam=" + (require_pam ? "on" : "off") +
                        " cache=" + cache_genome;
                    check_results_equal(expected.first, observed.first,
                                        context);
                    check(expected.second.guides ==
                              observed.second.guides,
                          context + ": guide summary mismatch");
                    check(expected.second.hits ==
                              observed.second.hits,
                          context + ": hit summary mismatch");
                    check(expected.second.candidates ==
                              observed.second.candidates,
                          context + ": candidate summary mismatch");
                    check(expected.second.seed_plan_guaranteed ==
                              observed.second.seed_plan_guaranteed,
                          context + ": seed plan mismatch");
                    check(expected.second.exhaustive_seed_plan ==
                              observed.second.exhaustive_seed_plan,
                          context + ": exhaustive plan mismatch");
                    check(expected.second.sequence_cache ==
                              observed.second.sequence_cache,
                          context + ": cache summary mismatch");
                    check(expected.second.memory_limit_mb == 0,
                          context + ": default memory limit mismatch");
                    check(expected.second.estimated_peak_mb > 0.0,
                          context + ": missing estimated peak");
                    check(expected.second.observed_peak_mb > 0.0,
                          context + ": missing observed peak");
                }
                if (!require_pam && max_bulge == 0 &&
                    cache_genome == "true") {
                    for (const offtarget::GuideResult& result :
                         expected.first) {
                        for (const offtarget::Hit& hit : result.hits) {
                            check(seen_hits
                                      .emplace(hit.target,
                                               hit.target_start,
                                               hit.target_end, hit.strand)
                                      .second,
                                  "duplicate hit key in repeat fixture");
                            saw_plus = saw_plus || hit.strand == "+";
                            saw_minus = saw_minus || hit.strand == "-";
                            saw_repeat =
                                saw_repeat || hit.target == "repeat2";
                        }
                    }
                }
            }
        }
    }
    check(saw_plus, "parallel fixture did not produce a plus-strand hit");
    check(saw_minus, "parallel fixture did not produce a minus-strand hit");
    check(saw_repeat, "repeated candidate fixture did not produce hits");
}

void test_memory_limit_preflight_and_cleanup() {
    TempDirectory temporary;
    const ParallelFixture fixture =
        write_parallel_fixture(temporary.path());

    offtarget::BuildOptions build_options;
    build_options.genome_path = fixture.fasta;
    build_options.prefix = fixture.prefix;
    build_options.k = 10;
    build_options.threads = 1;
    offtarget::build_index(build_options);

    const std::filesystem::path bounded_prefix =
        temporary.path() / "bounded_index";
    offtarget::BuildOptions bounded_options;
    bounded_options.genome_path = fixture.fasta;
    bounded_options.prefix = bounded_prefix;
    bounded_options.k = 10;
    bounded_options.threads = 1;
    bounded_options.max_memory_mb = 1024;
    const offtarget::BuildSummary bounded_summary =
        offtarget::build_index(bounded_options);
    check(bounded_summary.memory_limit_mb == 1024,
          "positive build memory limit was not recorded");
    check(bounded_summary.estimated_peak_mb <= 1024.0,
          "small fixture should fit a 1024 MiB build budget");
    check(std::filesystem::exists(
              std::filesystem::path(bounded_prefix.string() + ".ggi")),
          "positive build memory limit should produce an index");

    offtarget::SearchOptions search_options;
    search_options.genome_path = fixture.fasta;
    search_options.index_path = fixture.prefix;
    search_options.guides_path = fixture.guides;
    search_options.max_mismatch = 2;
    search_options.max_bulge = 0;
    search_options.seed_len = 10;
    search_options.threads = 2;
    search_options.cache_genome = "false";
    search_options.max_memory_mb = 1;
    offtarget::SearchSummary search_summary;
    bool search_failed = false;
    try {
        (void)offtarget::search_indexed(
            search_options, search_summary);
    } catch (const offtarget::OfftargetError& error) {
        search_failed = error.code() ==
                        offtarget::ExitCode::memory_limit;
        check(error.error_code() == "MEMORY_LIMIT_EXCEEDED",
              "unexpected search memory error code");
    }
    check(search_failed, "tiny search memory limit should fail before search");

    const std::filesystem::path limited_prefix =
        temporary.path() / "limited_index";
    offtarget::BuildOptions limited_options;
    limited_options.genome_path = fixture.fasta;
    limited_options.prefix = limited_prefix;
    limited_options.k = 10;
    limited_options.threads = 1;
    limited_options.max_memory_mb = 1;
    bool build_failed = false;
    try {
        (void)offtarget::build_index(limited_options);
    } catch (const offtarget::OfftargetError& error) {
        build_failed = error.code() ==
                       offtarget::ExitCode::memory_limit;
        check(error.error_code() == "MEMORY_LIMIT_EXCEEDED",
              "unexpected build memory error code");
    }
    check(build_failed, "tiny build memory limit should fail");
    for (const std::string suffix :
         {".positions.tmp", ".ggi.tmp", ".json.tmp"}) {
        check(!std::filesystem::exists(
                  std::filesystem::path(
                      limited_prefix.string() + suffix)),
              "memory failure left a temporary build file");
    }
}

void test_auto_cache_memory_budget() {
    constexpr std::uint64_t mib = 1024ULL * 1024ULL;
    check(offtarget::auto_sequence_cache_fits(
              5ULL * mib, 32, 4096),
          "small per-worker cache should fit");
    check(!offtarget::auto_sequence_cache_fits(
              600ULL * mib, 32, 34 * 1024),
          "32 copies of a 600 MiB genome should not fit 34 GiB");
    check(offtarget::auto_sequence_cache_fits(
              600ULL * mib, 8, 34 * 1024),
          "8 copies of a 600 MiB genome should fit 34 GiB");
    check(!offtarget::auto_sequence_cache_fits(
              5ULL * mib, 0, 4096),
          "zero workers cannot use a sequence cache");
    check(!offtarget::auto_sequence_cache_fits(
              0, 1, 4096),
          "empty genome cannot use a sequence cache");
}

void test_seed_encoding_and_plans() {
    std::uint32_t code = 0;
    check(offtarget::encode_kmer("ACGT", code), "ACGT should encode");
    check(code == 27, "ACGT base-4 encoding mismatch");
    check(!offtarget::encode_kmer("ACGN", code),
          "invalid k-mer should fail");

    const auto plan = offtarget::build_seed_plan(20, 4, 0, 12, 12);
    check(plan.guaranteed, "mismatch-only k=12 plan should be guaranteed");
    check(plan.segments.size() == 1, "unexpected segment count");
    check(plan.segments.front().allowed_mismatches == 4,
          "unexpected mismatch budget");

    const auto unavailable =
        offtarget::build_seed_plan(20, 4, 1, 12, 12);
    check(!unavailable.guaranteed,
          "k=12 bulge plan should be unavailable");
    const auto k10 = offtarget::build_seed_plan(20, 4, 1, 10, 10);
    check(k10.guaranteed, "k=10 bulge plan should be guaranteed");
}

void test_alignment_and_cigar() {
    const auto exact =
        offtarget::align_global("ACGTACGT", "ACGTACGT");
    check(exact.mismatches == 0, "exact alignment has mismatches");
    check(exact.indels() == 0, "exact alignment has indels");
    check(exact.cigar == "8M", "exact CIGAR mismatch");

    const auto deletion =
        offtarget::align_global("ACGTACGT", "ACGACGT");
    check(deletion.mismatches == 0, "deletion has mismatches");
    check(deletion.indels() == 1, "deletion count mismatch");
    check(deletion.cigar.find('I') != std::string::npos,
          "RNA-bulge CIGAR mismatch");

    const auto best = offtarget::best_alignment(
        "TTACGTACGTAA", "ACGTACGT", 2, 0, 0);
    check(best.has_value(), "best alignment should exist");
    check(best->target_start == 2, "best alignment start mismatch");
    check(best->target_end == 10, "best alignment end mismatch");
}

void test_iupac_pam() {
    const auto fetch = [](const std::string&, std::int64_t start,
                          std::int64_t end)
        -> std::optional<std::string> {
        if (start == 20 && end == 23) {
            return std::string("AGG");
        }
        return std::nullopt;
    };
    check(offtarget::pam_ok_span(
              "chr1", 0, 20, "+", "NGG", "3prime", fetch),
          "NGG should match AGG");
    check(!offtarget::pam_ok_span(
              "chr1", 0, 20, "+", "TTT", "3prime", fetch),
          "TTT should not match AGG");
}

void test_json_escaping() {
    const std::string value = "a\"b\\c\n";
    check(offtarget::json_quote(value) == "\"a\\\"b\\\\c\\n\"",
          "JSON escaping mismatch");
}

void test_reverse_complement() {
    check(offtarget::reverse_complement("ACGTUN") == "NAACGT",
          "reverse complement mismatch");
    check(offtarget::reverse_complement_gapped("A-CG") == "CG-T",
          "gapped reverse complement mismatch");
}

}  // namespace

int main() {
    test_parallel_search_determinism();
    test_auto_cache_memory_budget();
    test_memory_limit_preflight_and_cleanup();
    test_seed_encoding_and_plans();
    test_alignment_and_cigar();
    test_iupac_pam();
    test_json_escaping();
    test_reverse_complement();
    std::cout << "offtarget-engine unit tests passed\n";
    return 0;
}

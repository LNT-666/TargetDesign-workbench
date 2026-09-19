#include "offtarget/build_index.hpp"
#include "offtarget/error.hpp"
#include "offtarget/genome_index.hpp"
#include "offtarget/json_writer.hpp"
#include "offtarget/search.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

using offtarget::ExitCode;
using offtarget::OfftargetError;

std::string version_text() {
    return "offtarget-engine 0.1.0 index-format=1";
}

int default_threads() {
    const unsigned int available = std::thread::hardware_concurrency();
    return static_cast<int>(std::max(1U, std::min(available, 32U)));
}

int parse_int(const std::string& value, const std::string& option) {
    try {
        std::size_t consumed = 0;
        const int result = std::stoi(value, &consumed);
        if (consumed != value.size()) {
            throw std::invalid_argument("trailing characters");
        }
        return result;
    } catch (const std::exception&) {
        throw OfftargetError(ExitCode::usage, "INVALID_ARGUMENT",
                             option + " expects an integer");
    }
}

std::uint64_t parse_u64(const std::string& value,
                        const std::string& option) {
    if (value.empty() || value.front() == '-') {
        throw OfftargetError(
            ExitCode::usage, "INVALID_ARGUMENT",
            option + " expects a non-negative integer");
    }
    try {
        std::size_t consumed = 0;
        const std::uint64_t result = std::stoull(value, &consumed);
        if (consumed != value.size()) {
            throw std::invalid_argument("trailing characters");
        }
        return result;
    } catch (const std::exception&) {
        throw OfftargetError(ExitCode::usage, "INVALID_ARGUMENT",
                             option + " expects a non-negative integer");
    }
}

std::uint64_t environment_max_memory_mb() {
    const char* raw = std::getenv("PROGRAMFILE_MAX_MEMORY_MB");
    if (raw == nullptr || std::string(raw).empty()) {
        return 0;
    }
    return parse_u64(raw, "PROGRAMFILE_MAX_MEMORY_MB");
}

std::string next_value(int& index, int argc, char** argv,
                       const std::string& option) {
    if (index + 1 >= argc) {
        throw OfftargetError(ExitCode::usage, "MISSING_ARGUMENT",
                             option + " requires a value");
    }
    return argv[++index];
}

void print_capabilities() {
    std::cout
        << "{\n"
           "  \"engine\": \"indexed\",\n"
           "  \"implementation\": \"native-cpp\",\n"
           "  \"index_format\": 1,\n"
           "  \"max_build_k\": 12,\n"
           "  \"threads\": true,\n"
           "  \"max_memory_mb\": true,\n"
           "  \"indels\": \"dna_rna\",\n"
           "  \"pam_sides\": [\"3prime\", \"5prime\"]\n"
           "}\n";
}

int run_build(int argc, char** argv) {
    offtarget::BuildOptions options;
    options.threads = default_threads();
    bool have_genome = false;
    bool have_prefix = false;
    bool have_max_memory = false;
    std::uint64_t max_memory_mb = 0;
    for (int index = 0; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--genome") {
            options.genome_path = next_value(index, argc, argv, argument);
            have_genome = true;
        } else if (argument == "--prefix") {
            options.prefix = next_value(index, argc, argv, argument);
            have_prefix = true;
        } else if (argument == "--k") {
            options.k =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--threads") {
            options.threads =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--contigs") {
            options.contigs_path =
                next_value(index, argc, argv, argument);
        } else if (argument == "--force") {
            options.force = true;
        } else if (argument == "--output") {
            options.output_path =
                next_value(index, argc, argv, argument);
        } else if (argument == "--max-memory-mb") {
            max_memory_mb = parse_u64(
                next_value(index, argc, argv, argument), argument);
            have_max_memory = true;
        } else if (argument == "--help" || argument == "-h") {
            std::cout
                << "Usage: offtarget-engine build-index --genome PATH "
                   "--prefix PREFIX [--k 8..12] [--threads N] "
                   "[--contigs FILE] [--force] [--output PATH] "
                   "[--max-memory-mb N]\n";
            return 0;
        } else {
            throw OfftargetError(ExitCode::usage, "UNKNOWN_ARGUMENT",
                                 "Unknown build-index argument: " +
                                     argument);
        }
    }
    if (!have_genome || !have_prefix) {
        throw OfftargetError(
            ExitCode::usage, "MISSING_ARGUMENT",
            "build-index requires --genome and --prefix");
    }
    if (options.threads < 1) {
        throw OfftargetError(ExitCode::usage, "INVALID_THREADS",
                             "--threads must be >= 1");
    }
    options.max_memory_mb =
        have_max_memory ? max_memory_mb : environment_max_memory_mb();
    const offtarget::BuildSummary summary =
        offtarget::build_index(options);
    if (!options.output_path.has_value()) {
        std::cout << summary.json;
    }
    return 0;
}

int run_inspect(int argc, char** argv) {
    std::filesystem::path genome_path;
    std::filesystem::path index_path;
    bool have_genome = false;
    bool have_index = false;
    bool json_output = false;
    for (int index = 0; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--genome") {
            genome_path = next_value(index, argc, argv, argument);
            have_genome = true;
        } else if (argument == "--index") {
            index_path = next_value(index, argc, argv, argument);
            have_index = true;
        } else if (argument == "--json") {
            json_output = true;
        } else if (argument == "--help" || argument == "-h") {
            std::cout
                << "Usage: offtarget-engine inspect-index --genome PATH "
                   "--index PREFIX [--json]\n";
            return 0;
        } else {
            throw OfftargetError(ExitCode::usage, "UNKNOWN_ARGUMENT",
                                 "Unknown inspect-index argument: " +
                                     argument);
        }
    }
    if (!have_genome || !have_index) {
        throw OfftargetError(
            ExitCode::usage, "MISSING_ARGUMENT",
            "inspect-index requires --genome and --index");
    }
    (void)json_output;
    const offtarget::GenomeIndex index =
        offtarget::GenomeIndex::load(index_path);
    const bool valid = index.is_valid_for(genome_path);
    std::cout << "{\n"
              << "  \"valid\": " << (valid ? "true" : "false") << ",\n"
              << "  \"reason\": "
              << offtarget::json_quote(
                     valid ? "" : "index fingerprint does not match genome")
              << ",\n"
              << "  \"index_format\": 1,\n"
              << "  \"k\": " << index.k() << ",\n"
              << "  \"index_bytes\": " << index.index_bytes() << ",\n"
              << "  \"position_dtype\": "
              << offtarget::json_quote(index.position_dtype()) << "\n"
              << "}\n";
    return 0;
}

int run_search(int argc, char** argv) {
    offtarget::SearchOptions options;
    options.threads = default_threads();
    bool have_genome = false;
    bool have_index = false;
    bool have_guides = false;
    bool have_max_memory = false;
    std::uint64_t max_memory_mb = 0;
    for (int index = 0; index < argc; ++index) {
        const std::string argument = argv[index];
        if (argument == "--genome") {
            options.genome_path = next_value(index, argc, argv, argument);
            have_genome = true;
        } else if (argument == "--index") {
            options.index_path = next_value(index, argc, argv, argument);
            have_index = true;
        } else if (argument == "--guides") {
            options.guides_path = next_value(index, argc, argv, argument);
            have_guides = true;
        } else if (argument == "--output") {
            const std::string value =
                next_value(index, argc, argv, argument);
            if (value != "-") {
                options.output_path = value;
            }
        } else if (argument == "--max-mismatch") {
            options.max_mismatch =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--max-bulge") {
            options.max_bulge =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--seed-len") {
            options.seed_len =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--seed-mismatch") {
            options.seed_mismatch =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--seed-mismatch-max") {
            options.seed_mismatch_max =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--require-pam") {
            options.require_pam = true;
        } else if (argument == "--pam") {
            options.pam = next_value(index, argc, argv, argument);
        } else if (argument == "--pam-side") {
            options.pam_side = next_value(index, argc, argv, argument);
        } else if (argument == "--threads") {
            options.threads =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--cache-genome") {
            options.cache_genome =
                next_value(index, argc, argv, argument);
        } else if (argument == "--progress-every") {
            options.progress_every =
                parse_int(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--max-candidates") {
            options.max_candidates =
                parse_u64(next_value(index, argc, argv, argument), argument);
        } else if (argument == "--max-memory-mb") {
            max_memory_mb = parse_u64(
                next_value(index, argc, argv, argument), argument);
            have_max_memory = true;
        } else if (argument == "--help" || argument == "-h") {
            std::cout
                << "Usage: offtarget-engine search --genome PATH "
                   "--index PREFIX --guides GUIDES.tsv "
                   "[--output hits.jsonl] [--max-mismatch N] "
                   "[--max-bulge N] [--seed-len N] [--require-pam] "
                   "[--pam MOTIF] [--pam-side 3prime|5prime] "
                   "[--threads N] [--max-memory-mb N]\n";
            return 0;
        } else {
            throw OfftargetError(ExitCode::usage, "UNKNOWN_ARGUMENT",
                                 "Unknown search argument: " + argument);
        }
    }
    if (!have_genome || !have_index || !have_guides) {
        throw OfftargetError(
            ExitCode::usage, "MISSING_ARGUMENT",
            "search requires --genome, --index, and --guides");
    }
    if (options.max_mismatch < 0 || options.max_bulge < 0 ||
        options.seed_len < 1) {
        throw OfftargetError(
            ExitCode::usage, "INVALID_SEARCH_PARAMS",
            "max-mismatch, max-bulge, and seed-len must be non-negative "
            "with seed-len >= 1");
    }
    if (options.pam_side != "3prime" &&
        options.pam_side != "5prime") {
        throw OfftargetError(ExitCode::usage, "INVALID_PAM_SIDE",
                             "--pam-side must be 3prime or 5prime");
    }
    if (options.require_pam &&
        (!options.pam.has_value() || options.pam->empty())) {
        throw OfftargetError(ExitCode::usage, "MISSING_PAM",
                             "--require-pam requires --pam");
    }
    if (options.threads < 1 || options.progress_every < 0) {
        throw OfftargetError(
            ExitCode::usage, "INVALID_THREADS",
            "--threads must be >= 1 and --progress-every must be >= 0");
    }
    if (options.cache_genome != "auto" &&
        options.cache_genome != "true" &&
        options.cache_genome != "false") {
        throw OfftargetError(ExitCode::usage, "INVALID_CACHE_MODE",
                             "--cache-genome must be auto, true, or false");
    }
    options.max_memory_mb =
        have_max_memory ? max_memory_mb : environment_max_memory_mb();

    offtarget::SearchSummary summary;
    const std::vector<offtarget::GuideResult> results =
        offtarget::search_indexed(options, summary);
    std::ofstream file;
    std::ostream* output = &std::cout;
    if (options.output_path.has_value()) {
        if (options.output_path->has_parent_path()) {
            std::filesystem::create_directories(
                options.output_path->parent_path());
        }
        file.open(*options.output_path,
                  std::ios::binary | std::ios::trunc);
        if (!file) {
            throw OfftargetError(ExitCode::io, "WRITE_OUTPUT",
                                 "Cannot write search output: " +
                                     options.output_path->string());
        }
        output = &file;
    }
    const offtarget::GenomeIndex index =
        offtarget::GenomeIndex::load(options.index_path);
    offtarget::write_search_jsonl(*output, results, summary, index.k(),
                                  options.progress_every);
    return 0;
}

void print_usage() {
    std::cout
        << "Usage: offtarget-engine <command> [options]\n"
           "\n"
           "Commands:\n"
           "  build-index    Build a CRISPRGGI v1 index\n"
           "  inspect-index  Validate an index against a FASTA\n"
           "  search         Search guides against an existing index\n"
           "  capabilities   Print machine-readable capabilities\n"
           "\n"
           "Use '<command> --help' for command options.\n";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        print_usage();
        return static_cast<int>(ExitCode::usage);
    }
    const std::string command = argv[1];
    try {
        if (command == "--version") {
            std::cout << version_text() << '\n';
            return 0;
        }
        if (command == "--help" || command == "-h" || command == "help") {
            print_usage();
            return 0;
        }
        if (command == "capabilities") {
            for (int index = 2; index < argc; ++index) {
                const std::string argument = argv[index];
                if (argument != "--json" && argument != "--help" &&
                    argument != "-h") {
                    throw OfftargetError(
                        ExitCode::usage, "UNKNOWN_ARGUMENT",
                        "Unknown capabilities argument: " + argument);
                }
                if (argument == "--help" || argument == "-h") {
                    std::cout << "Usage: offtarget-engine capabilities "
                                 "[--json]\n";
                    return 0;
                }
            }
            print_capabilities();
            return 0;
        }
        if (command == "build-index") {
            return run_build(argc - 2, argv + 2);
        }
        if (command == "inspect-index") {
            return run_inspect(argc - 2, argv + 2);
        }
        if (command == "search") {
            return run_search(argc - 2, argv + 2);
        }
        throw OfftargetError(ExitCode::usage, "UNKNOWN_COMMAND",
                             "Unknown command: " + command);
    } catch (const OfftargetError& error) {
        std::cerr << "offtarget-engine: [" << error.error_code() << "] "
                  << error.what() << '\n';
        return static_cast<int>(error.code());
    } catch (const std::exception& error) {
        std::cerr << "offtarget-engine: internal error: " << error.what()
                  << '\n';
        return static_cast<int>(ExitCode::internal);
    }
}

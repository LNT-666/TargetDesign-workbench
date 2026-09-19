#include "offtarget/fasta.hpp"

#include "offtarget/error.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace offtarget {

namespace {

std::string trim_cr(std::string line) {
    if (!line.empty() && line.back() == '\r') {
        line.pop_back();
    }
    return line;
}

std::string first_token(const std::string& line) {
    std::size_t begin = 0;
    while (begin < line.size() &&
           std::isspace(static_cast<unsigned char>(line[begin]))) {
        ++begin;
    }
    std::size_t end = begin;
    while (end < line.size() &&
           !std::isspace(static_cast<unsigned char>(line[end]))) {
        ++end;
    }
    return line.substr(begin, end - begin);
}

}  // namespace

std::string uppercase_ascii(std::string value) {
    for (char& ch : value) {
        ch = static_cast<char>(
            std::toupper(static_cast<unsigned char>(ch)));
    }
    return value;
}

FastaFile::FastaFile(const std::filesystem::path& path) : path_(path) {
    if (!std::filesystem::is_regular_file(path_)) {
        throw OfftargetError(ExitCode::io, "MISSING_FASTA",
                             "Genome FASTA not found: " + path_.string());
    }
    fai_path_ = std::filesystem::path(path_.string() + ".fai");
    load_or_create_index();
    validate();
    input_.open(path_, std::ios::binary);
    if (!input_) {
        throw OfftargetError(ExitCode::io, "READ_FASTA",
                             "Cannot open FASTA: " + path_.string());
    }
}

void FastaFile::ensure_index_file() const {
    if (!std::filesystem::is_regular_file(fai_path_)) {
        create_index_file();
    }
}

void FastaFile::load_or_create_index() const {
    if (std::filesystem::is_regular_file(fai_path_)) {
        try {
            load_index_file();
            return;
        } catch (const std::exception&) {
            records_.clear();
            by_name_.clear();
            total_bases_ = 0;
        }
    }
    create_index_file();
    load_index_file();
}

void FastaFile::create_index_file() const {
    std::ifstream input(path_, std::ios::binary);
    if (!input) {
        throw OfftargetError(ExitCode::io, "READ_FASTA",
                             "Cannot open FASTA: " + path_.string());
    }

    std::vector<FastaRecord> records;
    FastaRecord current;
    bool have_record = false;
    std::string line;
    std::uint64_t line_start = 0;
    bool have_sequence_offset = false;

    while (std::getline(input, line)) {
        const std::streampos after_pos = input.tellg();
        const std::uint64_t after =
            after_pos == std::streampos(-1)
                ? std::filesystem::file_size(path_)
                : static_cast<std::uint64_t>(after_pos);
        line = trim_cr(line);

        if (!line.empty() && line.front() == '>') {
            if (have_record) {
                records.push_back(current);
            }
            current = FastaRecord{};
            current.name = first_token(line.substr(1));
            if (current.name.empty()) {
                throw OfftargetError(ExitCode::io, "EMPTY_FASTA_ID",
                                     "FASTA record has an empty identifier");
            }
            current.offset = after;
            have_record = true;
            have_sequence_offset = false;
            line_start = after;
            continue;
        }

        if (!have_record) {
            if (!line.empty()) {
                throw OfftargetError(
                    ExitCode::io, "MALFORMED_FASTA",
                    "FASTA sequence data appears before the first header");
            }
            line_start = after;
            continue;
        }

        if (!line.empty()) {
            const std::uint32_t width =
                static_cast<std::uint32_t>(after - line_start);
            const std::uint32_t bases =
                static_cast<std::uint32_t>(line.size());
            if (!have_sequence_offset) {
                current.offset = line_start;
                current.line_bases = bases;
                current.line_width = width;
                have_sequence_offset = true;
            } else if (current.line_bases == 0) {
                current.line_bases = bases;
                current.line_width = width;
            } else if (bases > current.line_bases) {
                throw OfftargetError(
                    ExitCode::io, "MALFORMED_FASTA",
                    "FASTA line is wider than the first sequence line in " +
                        current.name);
            }
            current.length += bases;
        }
        line_start = after;
    }

    if (have_record) {
        records.push_back(current);
    }
    if (records.empty()) {
        throw OfftargetError(ExitCode::io, "EMPTY_FASTA",
                             "No FASTA records found: " + path_.string());
    }
    for (const FastaRecord& record : records) {
        if (record.line_bases == 0 || record.line_width == 0) {
            throw OfftargetError(
                ExitCode::io, "EMPTY_FASTA_RECORD",
                "FASTA record has no sequence: " + record.name);
        }
    }

    std::ofstream output(fai_path_, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw OfftargetError(ExitCode::io, "WRITE_FAI",
                             "Cannot write FASTA index: " +
                                 fai_path_.string());
    }
    for (const FastaRecord& record : records) {
        output << record.name << '\t' << record.length << '\t'
               << record.offset << '\t' << record.line_bases << '\t'
               << record.line_width << '\n';
    }
}

void FastaFile::load_index_file() const {
    records_.clear();
    by_name_.clear();
    total_bases_ = 0;

    std::ifstream input(fai_path_);
    if (!input) {
        throw OfftargetError(ExitCode::io, "MISSING_FAI",
                             "FASTA index not found: " + fai_path_.string());
    }
    std::string line;
    std::uint64_t ordinal = 0;
    while (std::getline(input, line)) {
        line = trim_cr(line);
        if (line.empty()) {
            continue;
        }
        std::istringstream fields(line);
        FastaRecord record;
        std::string length;
        std::string offset;
        std::string line_bases;
        std::string line_width;
        if (!std::getline(fields, record.name, '\t') ||
            !std::getline(fields, length, '\t') ||
            !std::getline(fields, offset, '\t') ||
            !std::getline(fields, line_bases, '\t') ||
            !std::getline(fields, line_width, '\t')) {
            throw std::runtime_error("malformed .fai line");
        }
        record.length = std::stoull(length);
        record.offset = std::stoull(offset);
        record.line_bases = static_cast<std::uint32_t>(
            std::stoul(line_bases));
        record.line_width = static_cast<std::uint32_t>(
            std::stoul(line_width));
        if (record.name.empty() || record.line_bases == 0 ||
            record.line_width < record.line_bases) {
            throw std::runtime_error("invalid .fai fields");
        }
        if (by_name_.contains(record.name)) {
            throw std::runtime_error("duplicate .fai contig");
        }
        by_name_[record.name] = records_.size();
        records_.push_back(std::move(record));
        total_bases_ += records_.back().length;
        ++ordinal;
    }
    if (records_.empty()) {
        throw std::runtime_error("empty .fai");
    }
    (void)ordinal;
}

void FastaFile::validate() const {
    const std::uint64_t file_size = std::filesystem::file_size(path_);
    for (const FastaRecord& record : records_) {
        if (record.offset > file_size) {
            throw OfftargetError(ExitCode::io, "INVALID_FAI",
                                 "FASTA index offset is outside the file");
        }
        const std::uint64_t last_line =
            record.length == 0 ? 0 : (record.length - 1) / record.line_bases;
        if (record.offset +
                last_line * static_cast<std::uint64_t>(record.line_width) >
            file_size) {
            throw OfftargetError(ExitCode::io, "INVALID_FAI",
                                 "FASTA index extends past the file");
        }
    }
}

const FastaRecord* FastaFile::find_record(
    const std::string& name) const {
    const auto iterator = by_name_.find(name);
    if (iterator == by_name_.end()) {
        return nullptr;
    }
    return &records_[iterator->second];
}

std::optional<std::string> FastaFile::fetch(
    const std::string& name, std::uint64_t start,
    std::uint64_t end) const {
    const FastaRecord* record = find_record(name);
    if (record == nullptr) {
        return std::nullopt;
    }
    if (start >= record->length || end <= start) {
        return std::nullopt;
    }
    end = std::min(end, record->length);
    if (start >= end) {
        return std::nullopt;
    }

    const std::uint64_t last = end - 1;
    const std::uint64_t first_line = start / record->line_bases;
    const std::uint64_t last_line = last / record->line_bases;
    const std::uint64_t file_start =
        record->offset + first_line * record->line_width +
        start % record->line_bases;
    const std::uint64_t file_end =
        record->offset + last_line * record->line_width +
        (last % record->line_bases) + 1;
    if (file_end < file_start || !input_) {
        return std::nullopt;
    }
    const std::uint64_t raw_size = file_end - file_start;
    if (raw_size >
        static_cast<std::uint64_t>(
            std::numeric_limits<std::size_t>::max())) {
        return std::nullopt;
    }
    std::string raw(static_cast<std::size_t>(raw_size), '\0');
    input_.clear();
    input_.seekg(static_cast<std::streamoff>(file_start));
    if (!input_) {
        return std::nullopt;
    }
    input_.read(raw.data(), static_cast<std::streamsize>(raw.size()));
    if (input_.gcount() != static_cast<std::streamsize>(raw.size())) {
        return std::nullopt;
    }

    std::string sequence;
    sequence.reserve(static_cast<std::size_t>(end - start));
    for (const char ch : raw) {
        if (ch != '\n' && ch != '\r') {
            sequence.push_back(ch);
        }
    }
    return uppercase_ascii(std::move(sequence));
}

std::optional<std::string> FastaFile::fetch_all(
    const std::string& name) const {
    const FastaRecord* record = find_record(name);
    if (record == nullptr) {
        return std::nullopt;
    }
    return fetch(name, 0, record->length);
}

}  // namespace offtarget

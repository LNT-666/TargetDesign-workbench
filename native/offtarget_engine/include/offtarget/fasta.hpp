#pragma once

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace offtarget {

struct FastaRecord {
    std::string name;
    std::uint64_t length = 0;
    std::uint64_t offset = 0;
    std::uint32_t line_bases = 0;
    std::uint32_t line_width = 0;
};

class FastaFile {
public:
    explicit FastaFile(const std::filesystem::path& path);

    [[nodiscard]] const std::filesystem::path& path() const noexcept {
        return path_;
    }
    [[nodiscard]] const std::vector<FastaRecord>& records() const noexcept {
        return records_;
    }
    [[nodiscard]] const FastaRecord* find_record(
        const std::string& name) const;
    [[nodiscard]] std::optional<std::string> fetch(
        const std::string& name, std::uint64_t start,
        std::uint64_t end) const;
    [[nodiscard]] std::optional<std::string> fetch_all(
        const std::string& name) const;
    [[nodiscard]] std::uint64_t total_bases() const noexcept {
        return total_bases_;
    }

    void ensure_index_file() const;

private:
    void load_or_create_index() const;
    void create_index_file() const;
    void load_index_file() const;
    void validate() const;

    std::filesystem::path path_;
    std::filesystem::path fai_path_;
    mutable std::vector<FastaRecord> records_;
    mutable std::unordered_map<std::string, std::size_t> by_name_;
    mutable std::uint64_t total_bases_ = 0;
    mutable std::ifstream input_;
};

std::string uppercase_ascii(std::string value);

}  // namespace offtarget

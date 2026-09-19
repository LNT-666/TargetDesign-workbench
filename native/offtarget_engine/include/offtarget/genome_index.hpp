#pragma once

#include "offtarget/fasta.hpp"

#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

namespace offtarget {

constexpr std::uint8_t kIndexFormatVersion = 1;
constexpr char kIndexMagic[] = "CRISPRGGI";
constexpr std::size_t kIndexMagicSize = sizeof(kIndexMagic) - 1;

struct ContigRecord {
    std::string name;
    std::uint64_t start = 0;
    std::uint64_t length = 0;
};

class MappedFile {
public:
    MappedFile() = default;
    explicit MappedFile(const std::filesystem::path& path);
    ~MappedFile();

    MappedFile(const MappedFile&) = delete;
    MappedFile& operator=(const MappedFile&) = delete;
    MappedFile(MappedFile&& other) noexcept;
    MappedFile& operator=(MappedFile&& other) noexcept;

    [[nodiscard]] const std::uint8_t* data() const noexcept {
        return data_;
    }
    [[nodiscard]] std::size_t size() const noexcept { return size_; }

private:
    void reset() noexcept;

    std::uint8_t* data_ = nullptr;
    std::size_t size_ = 0;
#ifdef _WIN32
    void* file_handle_ = nullptr;
    void* mapping_handle_ = nullptr;
#else
    int fd_ = -1;
#endif
};

class GenomeIndex {
public:
    static GenomeIndex load(const std::filesystem::path& prefix);

    [[nodiscard]] std::string prefix() const { return prefix_.string(); }
    [[nodiscard]] std::string ggi_path() const {
        return (prefix_.string() + ".ggi");
    }
    [[nodiscard]] std::string metadata_path() const {
        return (prefix_.string() + ".json");
    }
    [[nodiscard]] std::uint32_t k() const noexcept { return k_; }
    [[nodiscard]] std::uint64_t total_bases() const noexcept {
        return total_bases_;
    }
    [[nodiscard]] const std::vector<ContigRecord>& contigs() const noexcept {
        return contigs_;
    }
    [[nodiscard]] std::uint64_t valid_count() const noexcept {
        return valid_count_;
    }
    [[nodiscard]] std::string position_dtype() const {
        return total_bases_ < (std::uint64_t{1} << 32) ? "u4" : "u8";
    }
    [[nodiscard]] std::uint64_t offset_count() const noexcept {
        return (std::uint64_t{1} << (2 * k_)) + 1;
    }
    [[nodiscard]] std::uint64_t offset(std::uint64_t code) const;
    [[nodiscard]] std::span<const std::uint8_t> positions_bytes(
        std::uint64_t code) const;
    [[nodiscard]] std::uint64_t position(std::uint64_t code,
                                         std::uint64_t index) const;
    [[nodiscard]] std::optional<std::pair<std::string, std::uint64_t>> locate(
        std::uint64_t global_position) const;
    [[nodiscard]] bool is_valid_for(
        const std::filesystem::path& genome_path) const;
    [[nodiscard]] std::optional<std::string> metadata_fingerprint() const;
    [[nodiscard]] std::uint64_t index_bytes() const noexcept {
        return mapped_.size();
    }
    [[nodiscard]] std::size_t position_width() const noexcept {
        return total_bases_ < (std::uint64_t{1} << 32) ? 4U : 8U;
    }

private:
    std::filesystem::path prefix_;
    std::uint32_t k_ = 0;
    std::uint64_t total_bases_ = 0;
    std::uint64_t valid_count_ = 0;
    std::vector<ContigRecord> contigs_;
    std::vector<std::uint64_t> contig_starts_;
    MappedFile mapped_;
    const std::uint8_t* offsets_bytes_ = nullptr;
    const std::uint8_t* positions_ = nullptr;
    std::size_t positions_bytes_ = 0;
};

std::filesystem::path normalize_index_prefix(
    const std::filesystem::path& path);
std::string genome_fingerprint(const std::filesystem::path& genome_path);
std::string sha256_hex(const std::uint8_t* data, std::size_t size);
std::string sha256_file_prefix_suffix(
    const std::filesystem::path& path, std::uint64_t size);
std::optional<std::string> read_json_string_value(
    const std::filesystem::path& json_path, const std::string& key);

}  // namespace offtarget

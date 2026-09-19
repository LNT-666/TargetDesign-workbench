#include "offtarget/genome_index.hpp"

#include "offtarget/error.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

#ifdef _WIN32
#define NOMINMAX
#include <Windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace offtarget {

namespace {

class ByteReader {
public:
    ByteReader(const std::uint8_t* data, std::size_t size)
        : data_(data), size_(size) {}

    template <typename T>
    T read() {
        static_assert(std::is_integral_v<T>);
        if (cursor_ + sizeof(T) > size_) {
            throw OfftargetError(ExitCode::io, "TRUNCATED_INDEX",
                                 "Index file is truncated");
        }
        T value{};
        std::memcpy(&value, data_ + cursor_, sizeof(T));
        cursor_ += sizeof(T);
        return value;
    }

    std::string read_string(std::size_t length) {
        if (cursor_ + length > size_) {
            throw OfftargetError(ExitCode::io, "TRUNCATED_INDEX",
                                 "Index file is truncated");
        }
        std::string value(
            reinterpret_cast<const char*>(data_ + cursor_), length);
        cursor_ += length;
        return value;
    }

    [[nodiscard]] std::size_t cursor() const noexcept { return cursor_; }

private:
    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t cursor_ = 0;
};

std::uint64_t read_le_u64(const std::uint8_t* data) {
    std::uint64_t value = 0;
    std::memcpy(&value, data, sizeof(value));
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    value = __builtin_bswap64(value);
#endif
    return value;
}

std::uint32_t read_le_u32(const std::uint8_t* data) {
    std::uint32_t value = 0;
    std::memcpy(&value, data, sizeof(value));
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    value = __builtin_bswap32(value);
#endif
    return value;
}

std::uint64_t file_size_or_throw(const std::filesystem::path& path) {
    std::error_code error;
    const std::uint64_t size = std::filesystem::file_size(path, error);
    if (error) {
        throw OfftargetError(ExitCode::io, "MISSING_FILE",
                             "Cannot stat file: " + path.string());
    }
    return size;
}

std::uint64_t mtime_ns(const std::filesystem::path& path) {
#ifdef _WIN32
    const std::wstring native = path.wstring();
    WIN32_FILE_ATTRIBUTE_DATA data{};
    if (!GetFileAttributesExW(native.c_str(), GetFileExInfoStandard,
                              &data)) {
        throw OfftargetError(ExitCode::io, "STAT_FILE",
                             "Cannot stat file: " + path.string());
    }
    ULARGE_INTEGER ticks{};
    ticks.LowPart = data.ftLastWriteTime.dwLowDateTime;
    ticks.HighPart = data.ftLastWriteTime.dwHighDateTime;
    constexpr std::uint64_t windows_to_unix_100ns = 116444736000000000ULL;
    if (ticks.QuadPart < windows_to_unix_100ns) {
        return 0;
    }
    return (ticks.QuadPart - windows_to_unix_100ns) * 100ULL;
#else
    struct stat status {};
    if (stat(path.c_str(), &status) != 0) {
        throw OfftargetError(ExitCode::io, "STAT_FILE",
                             "Cannot stat file: " + path.string());
    }
#if defined(__APPLE__)
    return static_cast<std::uint64_t>(status.st_mtimespec.tv_sec) *
               1000000000ULL +
           static_cast<std::uint64_t>(status.st_mtimespec.tv_nsec);
#else
    return static_cast<std::uint64_t>(status.st_mtim.tv_sec) *
               1000000000ULL +
           static_cast<std::uint64_t>(status.st_mtim.tv_nsec);
#endif
#endif
}

std::string hex_digest(const std::array<std::uint8_t, 32>& digest) {
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (const std::uint8_t value : digest) {
        out << std::setw(2) << static_cast<unsigned int>(value);
    }
    return out.str();
}

class Sha256 {
public:
    void update(const std::uint8_t* data, std::size_t size) {
        for (std::size_t index = 0; index < size; ++index) {
            buffer_[buffer_length_++] = data[index];
            if (buffer_length_ == buffer_.size()) {
                transform(buffer_.data());
                bit_length_ += 512;
                buffer_length_ = 0;
            }
        }
    }

    std::array<std::uint8_t, 32> finish() {
        const std::uint64_t total_bits = bit_length_ +
            static_cast<std::uint64_t>(buffer_length_) * 8ULL;
        buffer_[buffer_length_++] = 0x80;
        if (buffer_length_ > 56) {
            while (buffer_length_ < 64) {
                buffer_[buffer_length_++] = 0;
            }
            transform(buffer_.data());
            buffer_length_ = 0;
        }
        while (buffer_length_ < 56) {
            buffer_[buffer_length_++] = 0;
        }
        for (int index = 7; index >= 0; --index) {
            buffer_[buffer_length_++] = static_cast<std::uint8_t>(
                (total_bits >> (index * 8)) & 0xffU);
        }
        transform(buffer_.data());

        std::array<std::uint8_t, 32> result{};
        for (std::size_t index = 0; index < state_.size(); ++index) {
            result[index * 4 + 0] =
                static_cast<std::uint8_t>((state_[index] >> 24U) & 0xffU);
            result[index * 4 + 1] =
                static_cast<std::uint8_t>((state_[index] >> 16U) & 0xffU);
            result[index * 4 + 2] =
                static_cast<std::uint8_t>((state_[index] >> 8U) & 0xffU);
            result[index * 4 + 3] =
                static_cast<std::uint8_t>(state_[index] & 0xffU);
        }
        return result;
    }

private:
    static std::uint32_t rotate_right(std::uint32_t value,
                                      std::uint32_t count) {
        return (value >> count) | (value << (32U - count));
    }

    void transform(const std::uint8_t* chunk) {
        static constexpr std::array<std::uint32_t, 64> constants = {
            0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
            0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
            0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
            0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
            0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
            0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
            0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
            0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
            0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
            0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
            0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
            0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
            0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
            0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
            0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
            0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
        };

        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 16; ++index) {
            words[index] =
                (static_cast<std::uint32_t>(chunk[index * 4]) << 24U) |
                (static_cast<std::uint32_t>(chunk[index * 4 + 1]) << 16U) |
                (static_cast<std::uint32_t>(chunk[index * 4 + 2]) << 8U) |
                static_cast<std::uint32_t>(chunk[index * 4 + 3]);
        }
        for (std::size_t index = 16; index < words.size(); ++index) {
            const std::uint32_t s0 =
                rotate_right(words[index - 15], 7) ^
                rotate_right(words[index - 15], 18) ^
                (words[index - 15] >> 3U);
            const std::uint32_t s1 =
                rotate_right(words[index - 2], 17) ^
                rotate_right(words[index - 2], 19) ^
                (words[index - 2] >> 10U);
            words[index] = words[index - 16] + s0 + words[index - 7] + s1;
        }

        std::uint32_t a = state_[0];
        std::uint32_t b = state_[1];
        std::uint32_t c = state_[2];
        std::uint32_t d = state_[3];
        std::uint32_t e = state_[4];
        std::uint32_t f = state_[5];
        std::uint32_t g = state_[6];
        std::uint32_t h = state_[7];
        for (std::size_t index = 0; index < words.size(); ++index) {
            const std::uint32_t s1 =
                rotate_right(e, 6) ^ rotate_right(e, 11) ^
                rotate_right(e, 25);
            const std::uint32_t choice = (e & f) ^ ((~e) & g);
            const std::uint32_t temp1 =
                h + s1 + choice + constants[index] + words[index];
            const std::uint32_t s0 =
                rotate_right(a, 2) ^ rotate_right(a, 13) ^
                rotate_right(a, 22);
            const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t temp2 = s0 + majority;
            h = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }
        state_[0] += a;
        state_[1] += b;
        state_[2] += c;
        state_[3] += d;
        state_[4] += e;
        state_[5] += f;
        state_[6] += g;
        state_[7] += h;
    }

    std::array<std::uint32_t, 8> state_ = {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    };
    std::array<std::uint8_t, 64> buffer_{};
    std::size_t buffer_length_ = 0;
    std::uint64_t bit_length_ = 0;
};

void update_file_range(Sha256& digest, std::ifstream& input,
                       std::uint64_t offset, std::size_t size) {
    input.clear();
    input.seekg(static_cast<std::streamoff>(offset));
    if (!input) {
        return;
    }
    std::array<std::uint8_t, 65536> buffer{};
    std::size_t remaining = size;
    while (remaining > 0) {
        const std::size_t chunk = std::min(remaining, buffer.size());
        input.read(reinterpret_cast<char*>(buffer.data()),
                   static_cast<std::streamsize>(chunk));
        const std::streamsize got = input.gcount();
        if (got <= 0) {
            break;
        }
        digest.update(buffer.data(), static_cast<std::size_t>(got));
        remaining -= static_cast<std::size_t>(got);
    }
}

}  // namespace

MappedFile::MappedFile(const std::filesystem::path& path) {
    const std::uint64_t file_size = file_size_or_throw(path);
    if (file_size == 0 ||
        file_size > static_cast<std::uint64_t>(
                        std::numeric_limits<std::size_t>::max())) {
        throw OfftargetError(ExitCode::io, "EMPTY_INDEX",
                             "Index file is empty or too large: " +
                                 path.string());
    }
#ifdef _WIN32
    const std::wstring native = path.wstring();
    HANDLE file = CreateFileW(native.c_str(), GENERIC_READ,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        throw OfftargetError(ExitCode::io, "OPEN_INDEX",
                             "Cannot open index: " + path.string());
    }
    HANDLE mapping =
        CreateFileMappingW(file, nullptr, PAGE_READONLY, 0, 0, nullptr);
    if (mapping == nullptr) {
        CloseHandle(file);
        throw OfftargetError(ExitCode::io, "MAP_INDEX",
                             "Cannot memory-map index: " + path.string());
    }
    void* view = MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0);
    if (view == nullptr) {
        CloseHandle(mapping);
        CloseHandle(file);
        throw OfftargetError(ExitCode::io, "MAP_INDEX",
                             "Cannot map index view: " + path.string());
    }
    file_handle_ = file;
    mapping_handle_ = mapping;
    data_ = static_cast<std::uint8_t*>(view);
#else
    fd_ = ::open(path.c_str(), O_RDONLY);
    if (fd_ < 0) {
        throw OfftargetError(ExitCode::io, "OPEN_INDEX",
                             "Cannot open index: " + path.string());
    }
    void* view = ::mmap(nullptr, static_cast<std::size_t>(file_size),
                        PROT_READ, MAP_PRIVATE, fd_, 0);
    if (view == MAP_FAILED) {
        ::close(fd_);
        fd_ = -1;
        throw OfftargetError(ExitCode::io, "MAP_INDEX",
                             "Cannot memory-map index: " + path.string());
    }
    data_ = static_cast<std::uint8_t*>(view);
#endif
    size_ = static_cast<std::size_t>(file_size);
}

void MappedFile::reset() noexcept {
    if (data_ != nullptr) {
#ifdef _WIN32
        UnmapViewOfFile(data_);
#else
        ::munmap(data_, size_);
#endif
        data_ = nullptr;
    }
#ifdef _WIN32
    if (mapping_handle_ != nullptr) {
        CloseHandle(static_cast<HANDLE>(mapping_handle_));
        mapping_handle_ = nullptr;
    }
    if (file_handle_ != nullptr) {
        CloseHandle(static_cast<HANDLE>(file_handle_));
        file_handle_ = nullptr;
    }
#else
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
#endif
    size_ = 0;
}

MappedFile::~MappedFile() { reset(); }

MappedFile::MappedFile(MappedFile&& other) noexcept {
    data_ = other.data_;
    size_ = other.size_;
#ifdef _WIN32
    file_handle_ = other.file_handle_;
    mapping_handle_ = other.mapping_handle_;
    other.file_handle_ = nullptr;
    other.mapping_handle_ = nullptr;
#else
    fd_ = other.fd_;
    other.fd_ = -1;
#endif
    other.data_ = nullptr;
    other.size_ = 0;
}

MappedFile& MappedFile::operator=(MappedFile&& other) noexcept {
    if (this != &other) {
        reset();
        data_ = other.data_;
        size_ = other.size_;
#ifdef _WIN32
        file_handle_ = other.file_handle_;
        mapping_handle_ = other.mapping_handle_;
        other.file_handle_ = nullptr;
        other.mapping_handle_ = nullptr;
#else
        fd_ = other.fd_;
        other.fd_ = -1;
#endif
        other.data_ = nullptr;
        other.size_ = 0;
    }
    return *this;
}

std::filesystem::path normalize_index_prefix(
    const std::filesystem::path& path) {
    std::string value = path.string();
    if (value.ends_with(".ggi")) {
        value.resize(value.size() - 4);
    } else if (value.ends_with(".json")) {
        value.resize(value.size() - 5);
    }
    return value;
}

GenomeIndex GenomeIndex::load(const std::filesystem::path& path) {
    GenomeIndex index;
    index.prefix_ = normalize_index_prefix(path);
    const std::filesystem::path ggi =
        std::filesystem::path(index.prefix_.string() + ".ggi");
    const std::filesystem::path metadata =
        std::filesystem::path(index.prefix_.string() + ".json");
    if (!std::filesystem::is_regular_file(ggi)) {
        throw OfftargetError(ExitCode::io, "MISSING_INDEX",
                             "Index file not found: " + ggi.string());
    }
    if (!std::filesystem::is_regular_file(metadata)) {
        throw OfftargetError(ExitCode::io, "MISSING_METADATA",
                             "Index metadata not found: " +
                                 metadata.string());
    }

    index.mapped_ = MappedFile(ggi);
    ByteReader reader(index.mapped_.data(), index.mapped_.size());
    const std::string magic =
        reader.read_string(kIndexMagicSize);
    if (magic != std::string(kIndexMagic, kIndexMagicSize)) {
        throw OfftargetError(ExitCode::io, "BAD_MAGIC",
                             "Not a CRISPR genome index file");
    }
    const std::uint8_t version = reader.read<std::uint8_t>();
    if (version != kIndexFormatVersion) {
        throw OfftargetError(
            ExitCode::io, "UNSUPPORTED_INDEX_VERSION",
            "Unsupported index version: " + std::to_string(version));
    }
    index.k_ = reader.read<std::uint32_t>();
    if (index.k_ == 0 || index.k_ > 31) {
        throw OfftargetError(ExitCode::io, "INVALID_INDEX_K",
                             "Invalid index k value");
    }
    const std::uint32_t contig_count = reader.read<std::uint32_t>();
    index.total_bases_ = reader.read<std::uint64_t>();

    index.contigs_.reserve(contig_count);
    index.contig_starts_.reserve(contig_count);
    for (std::uint32_t ordinal = 0; ordinal < contig_count; ++ordinal) {
        const std::uint32_t name_length = reader.read<std::uint32_t>();
        ContigRecord contig;
        contig.name = reader.read_string(name_length);
        contig.start = reader.read<std::uint64_t>();
        contig.length = reader.read<std::uint64_t>();
        index.contig_starts_.push_back(contig.start);
        index.contigs_.push_back(std::move(contig));
    }
    if (!std::is_sorted(index.contig_starts_.begin(),
                        index.contig_starts_.end())) {
        throw OfftargetError(ExitCode::io, "INVALID_CONTIGS",
                             "Index contig starts are not sorted");
    }

    index.valid_count_ = reader.read<std::uint64_t>();
    const std::uint64_t offset_count =
        (std::uint64_t{1} << (2 * index.k_)) + 1;
    const std::uint64_t offsets_bytes =
        offset_count * static_cast<std::uint64_t>(sizeof(std::uint64_t));
    if (offsets_bytes >
        static_cast<std::uint64_t>(
            std::numeric_limits<std::size_t>::max()) ||
        reader.cursor() + static_cast<std::size_t>(offsets_bytes) >
            index.mapped_.size()) {
        throw OfftargetError(ExitCode::io, "TRUNCATED_OFFSETS",
                             "Index offsets table is truncated");
    }
    index.offsets_bytes_ = index.mapped_.data() + reader.cursor();
    const std::size_t positions_offset =
        reader.cursor() + static_cast<std::size_t>(offsets_bytes);
    const std::size_t position_width = index.position_width();
    if (position_width != 0 &&
        index.valid_count_ >
            (std::numeric_limits<std::uint64_t>::max() /
             position_width)) {
        throw OfftargetError(ExitCode::io, "INVALID_INDEX_SIZE",
                             "Index position table is too large");
    }
    const std::uint64_t position_bytes =
        index.valid_count_ * position_width;
    if (position_bytes >
            static_cast<std::uint64_t>(
                std::numeric_limits<std::size_t>::max()) ||
        positions_offset + static_cast<std::size_t>(position_bytes) >
            index.mapped_.size()) {
        throw OfftargetError(ExitCode::io, "TRUNCATED_POSITIONS",
                             "Index position table is truncated");
    }
    index.positions_ = index.mapped_.data() + positions_offset;
    index.positions_bytes_ =
        static_cast<std::size_t>(position_bytes);

    std::uint64_t previous = 0;
    for (std::uint64_t code = 0; code < offset_count; ++code) {
        const std::uint64_t value = index.offset(code);
        if (value < previous || value > index.valid_count_) {
            throw OfftargetError(ExitCode::io, "INVALID_OFFSETS",
                                 "Index offsets table is invalid");
        }
        previous = value;
    }
    if (offset_count > 0 && index.offset(offset_count - 1) !=
                               index.valid_count_) {
        throw OfftargetError(ExitCode::io, "INVALID_OFFSETS",
                             "Final index offset does not match "
                             "valid position count");
    }
    return index;
}

std::uint64_t GenomeIndex::offset(std::uint64_t code) const {
    if (code >= offset_count()) {
        throw std::out_of_range("k-mer code is outside offsets table");
    }
    return read_le_u64(offsets_bytes_ + code * sizeof(std::uint64_t));
}

std::span<const std::uint8_t> GenomeIndex::positions_bytes(
    std::uint64_t code) const {
    if (code + 1 >= offset_count()) {
        return {};
    }
    const std::uint64_t begin = offset(code);
    const std::uint64_t end = offset(code + 1);
    if (end <= begin || end > valid_count_) {
        return {};
    }
    const std::size_t width = position_width();
    return {positions_ + static_cast<std::size_t>(begin * width),
            static_cast<std::size_t>((end - begin) * width)};
}

std::uint64_t GenomeIndex::position(std::uint64_t code,
                                    std::uint64_t index) const {
    const std::span<const std::uint8_t> bytes = positions_bytes(code);
    const std::size_t width = position_width();
    if (index * width + width > bytes.size()) {
        throw std::out_of_range("position index is outside bucket");
    }
    if (width == 4) {
        return read_le_u32(bytes.data() + index * width);
    }
    return read_le_u64(bytes.data() + index * width);
}

std::optional<std::pair<std::string, std::uint64_t>>
GenomeIndex::locate(std::uint64_t global_position) const {
    if (contig_starts_.empty()) {
        return std::nullopt;
    }
    const auto iterator =
        std::upper_bound(contig_starts_.begin(), contig_starts_.end(),
                         global_position);
    if (iterator == contig_starts_.begin()) {
        return std::nullopt;
    }
    const std::size_t index =
        static_cast<std::size_t>(iterator - contig_starts_.begin() - 1);
    const ContigRecord& contig = contigs_[index];
    if (global_position < contig.start) {
        return std::nullopt;
    }
    const std::uint64_t local = global_position - contig.start;
    if (local >= contig.length) {
        return std::nullopt;
    }
    return std::make_pair(contig.name, local);
}

std::optional<std::string> GenomeIndex::metadata_fingerprint() const {
    return read_json_string_value(metadata_path(), "genome_fingerprint");
}

bool GenomeIndex::is_valid_for(
    const std::filesystem::path& genome_path) const {
    if (!std::filesystem::is_regular_file(genome_path)) {
        return false;
    }
    const std::optional<std::string> expected =
        metadata_fingerprint();
    if (!expected.has_value() || expected->empty()) {
        return false;
    }
    try {
        return *expected == genome_fingerprint(genome_path);
    } catch (const std::exception&) {
        return false;
    }
}

std::string sha256_hex(const std::uint8_t* data, std::size_t size) {
    Sha256 digest;
    digest.update(data, size);
    return hex_digest(digest.finish());
}

std::string sha256_file_prefix_suffix(
    const std::filesystem::path& path, std::uint64_t size) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw OfftargetError(ExitCode::io, "READ_FASTA",
                             "Cannot open FASTA: " + path.string());
    }
    Sha256 digest;
    const std::size_t block = 1U << 16U;
    update_file_range(digest, input, 0, block);
    const std::uint64_t last_offset = size > block ? size - block : 0;
    update_file_range(digest, input, last_offset, block);
    return hex_digest(digest.finish());
}

std::string genome_fingerprint(const std::filesystem::path& genome_path) {
    const std::uint64_t size = file_size_or_throw(genome_path);
    const std::uint64_t modified = mtime_ns(genome_path);
    Sha256 digest;
    const std::string stamp =
        std::to_string(size) + ":" + std::to_string(modified);
    digest.update(reinterpret_cast<const std::uint8_t*>(stamp.data()),
                  stamp.size());
    // The first/last blocks must be fed into the same hash as the stamp.
    std::ifstream input(genome_path, std::ios::binary);
    if (!input) {
        throw OfftargetError(ExitCode::io, "READ_FASTA",
                             "Cannot open FASTA: " + genome_path.string());
    }
    update_file_range(digest, input, 0, 1U << 16U);
    const std::uint64_t last_offset =
        size > (1U << 16U) ? size - (1U << 16U) : 0;
    update_file_range(digest, input, last_offset, 1U << 16U);
    return hex_digest(digest.finish());
}

std::optional<std::string> read_json_string_value(
    const std::filesystem::path& json_path, const std::string& key) {
    std::ifstream input(json_path, std::ios::binary);
    if (!input) {
        return std::nullopt;
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    const std::string text = buffer.str();
    const std::string needle = "\"" + key + "\"";
    std::size_t position = text.find(needle);
    if (position == std::string::npos) {
        return std::nullopt;
    }
    position += needle.size();
    while (position < text.size() &&
           std::isspace(static_cast<unsigned char>(text[position]))) {
        ++position;
    }
    if (position >= text.size() || text[position] != ':') {
        return std::nullopt;
    }
    ++position;
    while (position < text.size() &&
           std::isspace(static_cast<unsigned char>(text[position]))) {
        ++position;
    }
    if (position >= text.size() || text[position] != '"') {
        return std::nullopt;
    }
    ++position;
    std::string value;
    while (position < text.size()) {
        const char ch = text[position++];
        if (ch == '"') {
            return value;
        }
        if (ch != '\\') {
            value.push_back(ch);
            continue;
        }
        if (position >= text.size()) {
            return std::nullopt;
        }
        const char escaped = text[position++];
        switch (escaped) {
            case '"':
            case '\\':
            case '/':
                value.push_back(escaped);
                break;
            case 'b':
                value.push_back('\b');
                break;
            case 'f':
                value.push_back('\f');
                break;
            case 'n':
                value.push_back('\n');
                break;
            case 'r':
                value.push_back('\r');
                break;
            case 't':
                value.push_back('\t');
                break;
            default:
                return std::nullopt;
        }
    }
    return std::nullopt;
}

}  // namespace offtarget

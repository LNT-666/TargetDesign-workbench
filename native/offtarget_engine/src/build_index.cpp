#include "offtarget/build_index.hpp"

#include "offtarget/error.hpp"
#include "offtarget/fasta.hpp"
#include "offtarget/genome_index.hpp"
#include "offtarget/json_writer.hpp"
#include "offtarget/search.hpp"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

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

constexpr std::uint64_t kBuildChunkBases = 1U << 20U;
constexpr std::uint64_t kBuildMemoryCheckBases = 1U << 20U;
constexpr std::uint64_t kFixedBuildOverheadMb = 128ULL;

std::uint64_t bytes_to_mb_ceil(std::uint64_t bytes) noexcept {
    constexpr std::uint64_t mib = 1024ULL * 1024ULL;
    return bytes / mib + (bytes % mib == 0 ? 0ULL : 1ULL);
}

std::uint64_t saturating_add(std::uint64_t left,
                            std::uint64_t right) noexcept {
    if (left > std::numeric_limits<std::uint64_t>::max() - right) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return left + right;
}

std::uint64_t saturating_multiply(std::uint64_t left,
                                  std::uint64_t right) noexcept {
    if (left != 0 &&
        right > std::numeric_limits<std::uint64_t>::max() / left) {
        return std::numeric_limits<std::uint64_t>::max();
    }
    return left * right;
}

std::uint64_t estimate_build_peak_mb(
    std::uint64_t code_count, std::uint64_t valid_count,
    std::size_t position_width) noexcept {
    const std::uint64_t table_bytes = saturating_add(
        saturating_multiply(code_count, 24ULL),
        saturating_multiply(valid_count,
                            static_cast<std::uint64_t>(position_width) *
                                2ULL));
    return saturating_add(
        kFixedBuildOverheadMb, bytes_to_mb_ceil(table_bytes));
}

void enforce_build_memory_limit(
    std::uint64_t limit_mb, std::uint64_t estimated_peak_mb,
    const std::string& stage) {
    if (limit_mb == 0) {
        return;
    }
    if (estimated_peak_mb > limit_mb) {
        throw OfftargetError(
            ExitCode::memory_limit, "MEMORY_LIMIT_EXCEEDED",
            "Memory limit exceeded during build-index " + stage +
                ": estimated peak " +
                std::to_string(estimated_peak_mb) +
                " MiB exceeds --max-memory-mb=" +
                std::to_string(limit_mb) + " MiB");
    }
    const double observed_mb = current_rss_mb();
    if (observed_mb > static_cast<double>(limit_mb)) {
        throw OfftargetError(
            ExitCode::memory_limit, "MEMORY_LIMIT_EXCEEDED",
            "Memory limit exceeded during build-index " + stage +
                ": RSS " + std::to_string(observed_mb) +
                " MiB exceeds --max-memory-mb=" +
                std::to_string(limit_mb) + " MiB");
    }
}

class TemporaryBuildFiles {
public:
    explicit TemporaryBuildFiles(std::vector<std::filesystem::path> paths)
        : paths_(std::move(paths)) {}

    ~TemporaryBuildFiles() {
        if (dismissed_) {
            return;
        }
        std::error_code ignored;
        for (const std::filesystem::path& path : paths_) {
            std::filesystem::remove(path, ignored);
        }
    }

    TemporaryBuildFiles(const TemporaryBuildFiles&) = delete;
    TemporaryBuildFiles& operator=(const TemporaryBuildFiles&) = delete;

    void dismiss() noexcept { dismissed_ = true; }

private:
    std::vector<std::filesystem::path> paths_;
    bool dismissed_ = false;
};

class WritableMap {
public:
    WritableMap(const std::filesystem::path& path, std::uint64_t size) {
        if (size == 0) {
            return;
        }
#ifdef _WIN32
        const std::wstring native = path.wstring();
        HANDLE file = CreateFileW(native.c_str(), GENERIC_READ | GENERIC_WRITE,
                                  0, nullptr, CREATE_ALWAYS,
                                  FILE_ATTRIBUTE_NORMAL, nullptr);
        if (file == INVALID_HANDLE_VALUE) {
            throw OfftargetError(ExitCode::io, "CREATE_POSITIONS",
                                 "Cannot create positions file");
        }
        LARGE_INTEGER desired{};
        desired.QuadPart = static_cast<LONGLONG>(size);
        if (!SetFilePointerEx(file, desired, nullptr, FILE_BEGIN) ||
            !SetEndOfFile(file)) {
            CloseHandle(file);
            throw OfftargetError(ExitCode::io, "SIZE_POSITIONS",
                                 "Cannot size positions file");
        }
        HANDLE mapping =
            CreateFileMappingW(file, nullptr, PAGE_READWRITE,
                               static_cast<DWORD>(size >> 32U),
                               static_cast<DWORD>(size & 0xffffffffU),
                               nullptr);
        if (mapping == nullptr) {
            CloseHandle(file);
            throw OfftargetError(ExitCode::io, "MAP_POSITIONS",
                                 "Cannot map positions file");
        }
        void* view = MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, 0);
        if (view == nullptr) {
            CloseHandle(mapping);
            CloseHandle(file);
            throw OfftargetError(ExitCode::io, "MAP_POSITIONS",
                                 "Cannot map positions view");
        }
        file_handle_ = file;
        mapping_handle_ = mapping;
        data_ = static_cast<std::uint8_t*>(view);
#else
        fd_ = ::open(path.c_str(), O_RDWR | O_CREAT | O_TRUNC, 0644);
        if (fd_ < 0) {
            throw OfftargetError(ExitCode::io, "CREATE_POSITIONS",
                                 "Cannot create positions file");
        }
        if (::ftruncate(fd_, static_cast<off_t>(size)) != 0) {
            ::close(fd_);
            fd_ = -1;
            throw OfftargetError(ExitCode::io, "SIZE_POSITIONS",
                                 "Cannot size positions file");
        }
        void* view = ::mmap(nullptr, static_cast<std::size_t>(size),
                            PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
        if (view == MAP_FAILED) {
            ::close(fd_);
            fd_ = -1;
            throw OfftargetError(ExitCode::io, "MAP_POSITIONS",
                                 "Cannot map positions file");
        }
        data_ = static_cast<std::uint8_t*>(view);
#endif
        size_ = static_cast<std::size_t>(size);
    }

    ~WritableMap() { reset(); }
    WritableMap(const WritableMap&) = delete;
    WritableMap& operator=(const WritableMap&) = delete;

    [[nodiscard]] std::uint8_t* data() const noexcept { return data_; }
    [[nodiscard]] std::size_t size() const noexcept { return size_; }

    void flush() {
        if (data_ == nullptr || size_ == 0) {
            return;
        }
#ifdef _WIN32
        if (!FlushViewOfFile(data_, 0)) {
            throw OfftargetError(ExitCode::io, "FLUSH_POSITIONS",
                                 "Cannot flush positions mapping");
        }
#else
        if (::msync(data_, size_, MS_SYNC) != 0) {
            throw OfftargetError(ExitCode::io, "FLUSH_POSITIONS",
                                 "Cannot flush positions mapping");
        }
#endif
    }

private:
    void reset() noexcept {
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

    std::uint8_t* data_ = nullptr;
    std::size_t size_ = 0;
#ifdef _WIN32
    void* file_handle_ = nullptr;
    void* mapping_handle_ = nullptr;
#else
    int fd_ = -1;
#endif
};

struct SelectedContig {
    std::string name;
    std::uint64_t length = 0;
    std::uint64_t start = 0;
};

std::string trim(std::string value) {
    while (!value.empty() &&
           std::isspace(static_cast<unsigned char>(value.front()))) {
        value.erase(value.begin());
    }
    while (!value.empty() &&
           std::isspace(static_cast<unsigned char>(value.back()))) {
        value.pop_back();
    }
    return value;
}

std::set<std::string> read_contig_filter(
    const std::optional<std::filesystem::path>& path) {
    if (!path.has_value()) {
        return {};
    }
    std::ifstream input(*path);
    if (!input) {
        throw OfftargetError(ExitCode::io, "MISSING_CONTIGS",
                             "Contig filter not found: " +
                                 path->string());
    }
    std::set<std::string> selected;
    std::string line;
    while (std::getline(input, line)) {
        line = trim(std::move(line));
        if (!line.empty()) {
            selected.insert(line);
        }
    }
    return selected;
}

template <typename Callback>
void for_each_kmer(const FastaFile& genome,
                   const SelectedContig& contig, int k,
                   Callback callback) {
    if (contig.length < static_cast<std::uint64_t>(k)) {
        return;
    }
    const std::uint32_t mask =
        static_cast<std::uint32_t>((std::uint64_t{1} << (2 * k)) - 1);
    std::uint64_t chunk_start = 0;
    while (chunk_start < contig.length) {
        const std::uint64_t chunk_end =
            std::min(contig.length, chunk_start + kBuildChunkBases);
        const std::uint64_t fetch_end = std::min(
            contig.length, chunk_end + static_cast<std::uint64_t>(k - 1));
        const std::optional<std::string> maybe_sequence =
            genome.fetch(contig.name, chunk_start, fetch_end);
        if (!maybe_sequence.has_value()) {
            throw OfftargetError(ExitCode::io, "READ_FASTA",
                                 "Cannot read FASTA record: " +
                                     contig.name);
        }
        const std::string& sequence = *maybe_sequence;
        std::uint32_t rolling = 0;
        int valid = 0;
        for (std::uint64_t local = chunk_start;
             local < fetch_end; ++local) {
            std::uint32_t base = 0;
            const char raw =
                sequence[static_cast<std::size_t>(local - chunk_start)];
            switch (raw) {
                case 'A':
                case 'a':
                    base = 0;
                    break;
                case 'C':
                case 'c':
                    base = 1;
                    break;
                case 'G':
                case 'g':
                    base = 2;
                    break;
                case 'T':
                case 't':
                case 'U':
                case 'u':
                    base = 3;
                    break;
                default:
                    rolling = 0;
                    valid = 0;
                    continue;
            }
            rolling = ((rolling << 2U) | base) & mask;
            ++valid;
            if (valid >= k) {
                const std::uint64_t window_start =
                    local - static_cast<std::uint64_t>(k - 1);
                if (window_start >= chunk_start &&
                    window_start < chunk_end) {
                    callback(rolling,
                             contig.start + window_start);
                }
            }
        }
        chunk_start = chunk_end;
    }
}

template <typename T>
void write_binary(std::ostream& output, const T& value) {
    static_assert(std::is_trivially_copyable_v<T>);
    output.write(reinterpret_cast<const char*>(&value), sizeof(T));
}

void write_positions_file(std::ofstream& output,
                          const std::filesystem::path& positions_path,
                          std::uint64_t valid_count,
                          std::size_t width) {
    std::ifstream positions(positions_path, std::ios::binary);
    if (!positions) {
        throw OfftargetError(ExitCode::io, "READ_POSITIONS",
                             "Cannot read temporary positions file");
    }
    std::vector<char> buffer(1U << 20U);
    std::uint64_t remaining = valid_count * width;
    while (remaining > 0) {
        const std::size_t chunk = static_cast<std::size_t>(
            std::min<std::uint64_t>(remaining, buffer.size()));
        positions.read(buffer.data(),
                       static_cast<std::streamsize>(chunk));
        if (positions.gcount() != static_cast<std::streamsize>(chunk)) {
            throw OfftargetError(ExitCode::io, "READ_POSITIONS",
                                 "Temporary positions file is truncated");
        }
        output.write(buffer.data(),
                     static_cast<std::streamsize>(chunk));
        remaining -= chunk;
    }
}

void fsync_path(const std::filesystem::path& path) {
#ifdef _WIN32
    const std::wstring native = path.wstring();
    HANDLE handle = CreateFileW(native.c_str(), GENERIC_READ,
                                FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                                OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL,
                                nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        return;
    }
    FlushFileBuffers(handle);
    CloseHandle(handle);
#else
    const int fd = ::open(path.c_str(), O_RDONLY);
    if (fd >= 0) {
        ::fsync(fd);
        ::close(fd);
    }
#endif
}

void replace_file(const std::filesystem::path& temporary,
                  const std::filesystem::path& destination) {
#ifdef _WIN32
    std::error_code ignored;
    std::filesystem::remove(destination, ignored);
#endif
    std::error_code error;
    std::filesystem::rename(temporary, destination, error);
    if (error) {
        throw OfftargetError(ExitCode::io, "RENAME_INDEX",
                             "Cannot move temporary file into place: " +
                                 error.message());
    }
}

}  // namespace

BuildSummary build_index(const BuildOptions& options) {
    const auto start_time = std::chrono::steady_clock::now();
    if (options.k < 8 || options.k > 12) {
        throw OfftargetError(ExitCode::usage, "INVALID_K",
                             "build-index supports k in 8..12");
    }
    if (!std::filesystem::is_regular_file(options.genome_path)) {
        throw OfftargetError(ExitCode::io, "MISSING_FASTA",
                             "Genome FASTA not found: " +
                                 options.genome_path.string());
    }
    const std::filesystem::path prefix =
        normalize_index_prefix(options.prefix);
    const std::filesystem::path ggi_path =
        std::filesystem::path(prefix.string() + ".ggi");
    const std::filesystem::path metadata_path =
        std::filesystem::path(prefix.string() + ".json");
    const std::filesystem::path positions_path =
        std::filesystem::path(prefix.string() + ".positions.tmp");
    const std::filesystem::path ggi_tmp =
        std::filesystem::path(ggi_path.string() + ".tmp");
    const std::filesystem::path metadata_tmp =
        std::filesystem::path(metadata_path.string() + ".tmp");
    TemporaryBuildFiles temporary_files(
        {positions_path, ggi_tmp, metadata_tmp});
    if (!options.force &&
        (std::filesystem::exists(ggi_path) ||
         std::filesystem::exists(metadata_path))) {
        throw OfftargetError(
            ExitCode::io, "INDEX_EXISTS",
            "Index already exists; pass --force to rebuild: " +
                prefix.string());
    }
    if (prefix.has_parent_path()) {
        std::filesystem::create_directories(prefix.parent_path());
    }

    FastaFile genome(options.genome_path);
    const std::set<std::string> filter =
        read_contig_filter(options.contigs_path);
    std::vector<SelectedContig> selected;
    std::uint64_t total_bases = 0;
    for (const FastaRecord& record : genome.records()) {
        if (!filter.empty() && !filter.contains(record.name)) {
            continue;
        }
        selected.push_back(
            SelectedContig{record.name, record.length, total_bases});
        total_bases += record.length;
    }
    if (selected.empty()) {
        throw OfftargetError(ExitCode::io, "NO_CONTIGS",
                             "No sequences matched the requested contigs");
    }

    const std::size_t width = total_bases < (std::uint64_t{1} << 32)
                                  ? 4U
                                  : 8U;
    const std::uint64_t code_count = std::uint64_t{1} << (2 * options.k);
    enforce_build_memory_limit(
        options.max_memory_mb,
        estimate_build_peak_mb(code_count, 0, width), "counts");
    const auto counts_start = std::chrono::steady_clock::now();
    std::vector<std::uint64_t> counts(
        static_cast<std::size_t>(code_count), 0);
    for (const SelectedContig& contig : selected) {
        for_each_kmer(
            genome, contig, options.k,
            [&](std::uint32_t code, std::uint64_t /*position*/) {
                ++counts[code];
            });
    }
    enforce_build_memory_limit(
        options.max_memory_mb,
        estimate_build_peak_mb(code_count, 0, width), "offsets");
    std::vector<std::uint64_t> offsets(
        static_cast<std::size_t>(code_count + 1), 0);
    for (std::uint64_t code = 0; code < code_count; ++code) {
        offsets[code + 1] = offsets[code] + counts[code];
    }
    enforce_build_memory_limit(
        options.max_memory_mb,
        estimate_build_peak_mb(code_count, 0, width), "offsets");
    const std::uint64_t valid_count = offsets.back();
    const auto counts_end = std::chrono::steady_clock::now();
    if (valid_count == 0) {
        throw OfftargetError(
            ExitCode::io, "NO_VALID_KMERS",
            "No valid ACGT k-mers found for k=" +
                std::to_string(options.k));
    }

    if (valid_count >
        std::numeric_limits<std::uint64_t>::max() / width) {
        throw OfftargetError(ExitCode::io, "INDEX_TOO_LARGE",
                             "Position table is too large");
    }
    const std::uint64_t estimated_peak_mb =
        estimate_build_peak_mb(code_count, valid_count, width);
    enforce_build_memory_limit(
        options.max_memory_mb, estimated_peak_mb, "postings");
    std::filesystem::remove(positions_path);
    const auto fill_start = std::chrono::steady_clock::now();
    {
        WritableMap positions(positions_path, valid_count * width);
        std::vector<std::uint64_t> cursors = offsets;
        cursors.pop_back();
        std::uint64_t checked_bases = 0;
        for (const SelectedContig& contig : selected) {
            for_each_kmer(
                genome, contig, options.k,
                [&](std::uint32_t code, std::uint64_t position) {
                    if (++checked_bases % kBuildMemoryCheckBases == 0) {
                        enforce_build_memory_limit(
                            options.max_memory_mb, estimated_peak_mb,
                            "postings");
                    }
                    const std::uint64_t slot = cursors[code]++;
                    std::uint8_t* destination =
                        positions.data() + slot * width;
                    if (width == 4) {
                        const std::uint32_t value =
                            static_cast<std::uint32_t>(position);
                        std::memcpy(destination, &value, sizeof(value));
                    } else {
                        std::memcpy(destination, &position,
                                    sizeof(position));
                    }
                });
        }
        positions.flush();
    }
    enforce_build_memory_limit(
        options.max_memory_mb, estimated_peak_mb, "temporary files");
    const auto fill_end = std::chrono::steady_clock::now();

    enforce_build_memory_limit(
        options.max_memory_mb, estimated_peak_mb, "index output");
    {
        std::ofstream output(ggi_tmp,
                             std::ios::binary | std::ios::trunc);
        if (!output) {
            throw OfftargetError(ExitCode::io, "WRITE_INDEX",
                                 "Cannot write index temporary file");
        }
        output.write(kIndexMagic, kIndexMagicSize);
        write_binary(output, kIndexFormatVersion);
        const std::uint32_t k = static_cast<std::uint32_t>(options.k);
        const std::uint32_t contig_count =
            static_cast<std::uint32_t>(selected.size());
        write_binary(output, k);
        write_binary(output, contig_count);
        write_binary(output, total_bases);
        for (const SelectedContig& contig : selected) {
            const std::uint32_t name_length =
                static_cast<std::uint32_t>(contig.name.size());
            write_binary(output, name_length);
            output.write(contig.name.data(),
                         static_cast<std::streamsize>(contig.name.size()));
            write_binary(output, contig.start);
            write_binary(output, contig.length);
        }
        write_binary(output, valid_count);
        output.write(
            reinterpret_cast<const char*>(offsets.data()),
            static_cast<std::streamsize>(
                offsets.size() * sizeof(std::uint64_t)));
        write_positions_file(output, positions_path, valid_count, width);
        output.close();
    }
    fsync_path(ggi_tmp);
    enforce_build_memory_limit(
        options.max_memory_mb, estimated_peak_mb, "index output");

    const double elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() -
                                      start_time)
            .count();
    const std::string fingerprint =
        genome_fingerprint(options.genome_path);
    const std::uint64_t genome_bytes =
        std::filesystem::file_size(options.genome_path);
    const std::uint64_t index_bytes =
        std::filesystem::file_size(ggi_tmp);
    const double counts_seconds =
        std::chrono::duration<double>(counts_end - counts_start).count();
    const double fill_seconds =
        std::chrono::duration<double>(fill_end - fill_start).count();

    std::ostringstream json;
    json << "{\n"
         << "  \"format\": \"crispr-genome-index\",\n"
         << "  \"version\": 1,\n"
         << "  \"k\": " << options.k << ",\n"
         << "  \"genome\": "
         << json_quote(std::filesystem::absolute(options.genome_path)
                           .string())
         << ",\n"
         << "  \"genome_fingerprint\": " << json_quote(fingerprint)
         << ",\n"
         << "  \"genome_bytes\": " << genome_bytes << ",\n"
         << "  \"total_bases\": " << total_bases << ",\n"
         << "  \"valid_kmer_positions\": " << valid_count << ",\n"
         << "  \"contig_count\": " << selected.size() << ",\n"
         << "  \"contigs\": [";
    for (std::size_t index = 0; index < selected.size(); ++index) {
        const SelectedContig& contig = selected[index];
        if (index > 0) {
            json << ',';
        }
        json << "{\"id\":" << json_quote(contig.name)
             << ",\"start\":" << contig.start
             << ",\"length\":" << contig.length << '}';
    }
    json << "],\n"
         << "  \"position_dtype\": "
         << json_quote(width == 4 ? "u4" : "u8") << ",\n"
         << "  \"build_time_s\": " << std::fixed << std::setprecision(3)
         << elapsed << ",\n"
         << "  \"memory_peak_mb\": " << std::setprecision(2)
         << peak_rss_mb() << ",\n"
         << "  \"memory_limit_mb\": " << options.max_memory_mb << ",\n"
         << "  \"estimated_peak_mb\": " << std::setprecision(2)
         << estimated_peak_mb << ",\n"
         << "  \"observed_peak_mb\": " << std::setprecision(2)
         << peak_rss_mb() << ",\n"
         << "  \"index_bytes\": " << index_bytes << ",\n"
         << "  \"producer\": \"native-cpp\",\n"
         << "  \"producer_version\": \"0.1.0\",\n"
         << "  \"threads\": " << options.threads << ",\n"
         << "  \"counts_time_s\": " << std::setprecision(3)
         << counts_seconds << ",\n"
         << "  \"fill_time_s\": " << fill_seconds << "\n"
         << "}\n";
    {
        std::ofstream metadata(metadata_tmp,
                               std::ios::binary | std::ios::trunc);
        if (!metadata) {
            throw OfftargetError(ExitCode::io, "WRITE_METADATA",
                                 "Cannot write metadata temporary file");
        }
        metadata << json.str();
        metadata.close();
    }
    fsync_path(metadata_tmp);

    replace_file(ggi_tmp, ggi_path);
    replace_file(metadata_tmp, metadata_path);
    if (options.output_path.has_value()) {
        if (options.output_path->has_parent_path()) {
            std::filesystem::create_directories(
                options.output_path->parent_path());
        }
        std::ofstream output(*options.output_path,
                             std::ios::binary | std::ios::trunc);
        if (!output) {
            throw OfftargetError(ExitCode::io, "WRITE_REPORT",
                                 "Cannot write build report");
        }
        output << json.str();
    }
    std::error_code ignored;
    std::filesystem::remove(positions_path, ignored);

    BuildSummary summary;
    summary.k = options.k;
    summary.total_bases = total_bases;
    summary.valid_kmer_positions = valid_count;
    summary.contig_count = selected.size();
    summary.position_dtype = width == 4 ? "u4" : "u8";
    summary.build_time_s = elapsed;
    summary.memory_limit_mb = options.max_memory_mb;
    summary.estimated_peak_mb =
        static_cast<double>(estimated_peak_mb);
    summary.observed_peak_mb = peak_rss_mb();
    summary.memory_peak_mb = summary.observed_peak_mb;
    summary.index_bytes = index_bytes;
    summary.json = json.str();
    temporary_files.dismiss();
    return summary;
}

}  // namespace offtarget

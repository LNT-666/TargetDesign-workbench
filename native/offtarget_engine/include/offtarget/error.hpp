#pragma once

#include <stdexcept>
#include <string>

namespace offtarget {

enum class ExitCode : int {
    success = 0,
    usage = 2,
    unsupported = 3,
    io = 4,
    internal = 5,
    memory_limit = 6,
};

class OfftargetError : public std::runtime_error {
public:
    OfftargetError(ExitCode code, std::string error_code,
                   const std::string& message)
        : std::runtime_error(message),
          code_(code),
          error_code_(std::move(error_code)) {}

    [[nodiscard]] ExitCode code() const noexcept { return code_; }
    [[nodiscard]] const std::string& error_code() const noexcept {
        return error_code_;
    }

private:
    ExitCode code_;
    std::string error_code_;
};

}  // namespace offtarget

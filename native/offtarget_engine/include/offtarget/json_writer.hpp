#pragma once

#include <cstdint>
#include <string>

namespace offtarget {

std::string json_escape(const std::string& value);
std::string json_quote(const std::string& value);

}  // namespace offtarget

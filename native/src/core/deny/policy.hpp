#pragma once

#include <string_view>

namespace hide {

inline bool valid_name(std::string_view name, bool process) {
    if (name.empty() || name.size() > 255) return false;
    bool dot = false;
    for (unsigned char c : name) {
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '_') continue;
        if (c == '.') { dot = true; continue; }
        if (process && c == ':') continue;
        return false;
    }
    return process || (dot && name.front() != '.' && name.back() != '.');
}

inline bool valid_pair(std::string_view package, std::string_view process) {
    if (package == "webview_zygote") return process == package;
    return (package == "isolated" || valid_name(package, false)) && valid_name(process, true);
}

// Isolated selections are prefixes, separated at an Android process-name
// boundary. com.example must never match com.example.other's service.
inline bool isolated_match(std::string_view process, std::string_view prefix) {
    return !prefix.empty() && (process == prefix || (process.starts_with(prefix) &&
        (prefix.back() == ':' || process[prefix.size()] == ':')));
}

inline bool unmount(bool inverse, bool selected, bool automatic) {
    return !automatic && (inverse ? !selected : selected);
}

}

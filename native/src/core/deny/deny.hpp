#pragma once

#include <string_view>

#define ISOLATED_MAGIC "isolated"
#define WEBVIEW_ZYGOTE_MAGIC "webview_zygote"
#define WEBVIEW_ZYGOTE_UID 1053

namespace DenyRequest {
enum : int {
    ENFORCE,
    DISABLE,
    ADD,
    REMOVE,
    LIST,
    STATUS,

    MODE,
    CHECK,
    PROVIDER,

    END
};
}

namespace DenyResponse {
enum : int {
    OK,
    ENFORCED,
    NOT_ENFORCED,
    ITEM_EXIST,
    ITEM_NOT_EXIST,
    INVALID_PKG,
    NO_NS,
    ERROR,

    REBOOT_REQUIRED,
    UNSUPPORTED_PROVIDER,

    END
};
}

// CLI entries
int enable_deny();
int disable_deny();
int add_list(int client);
int rm_list(int client);
void ls_list(int client);

bool proc_context_match(int pid, std::string_view context);
void *logcat(void *arg);
extern bool logcat_exit;
bool start_hide_monitor();
bool is_sulist_enabled();
bool is_hide_ready();
int change_list(int client, bool remove, bool use_allow);
void list_selection(int client, bool use_allow);
int set_hide_mode(bool sulist);
int set_hide_provider(bool external);
bool is_external_hide();
bool is_hide_enabled();

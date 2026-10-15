#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
#include <set>
#include <map>

#include <consts.hpp>
#include <sqlite.hpp>
#include <core.hpp>

#include "deny.hpp"
#include "policy.hpp"

using namespace std;

struct Selection {
    map<string, set<string, StringCmp>, StringCmp> packages;
    map<int, set<string>> uids;
};

static Selection deny, allow;
static bool loaded = false;
static pthread_mutex_t data_lock = PTHREAD_MUTEX_INITIALIZER;
atomic<bool> denylist_enforced = false;
static atomic<bool> inverse = false;
static atomic<bool> ready = false;
static atomic<bool> external_at_boot = false;
static atomic<bool> external_owner = false;
static atomic<bool> hide_enabled = false;

bool is_external_hide() { return external_owner; }
bool is_hide_enabled() { return hide_enabled; }

static bool external_adapter_installed() {
    // The distributed source adapter installs this declaration. It is a root
    // module capability, not proof of injection health or a security boundary.
    return access("/data/adb/modules/rezygisk/kitsune-hide-v1", F_OK) == 0 &&
        access("/data/adb/modules/rezygisk/disable", F_OK) != 0 &&
        access("/data/adb/modules/rezygisk/remove", F_OK) != 0;
}

static bool external_provider_installed() {
    // Known unadapted providers own their clean namespace. Unknown root modules
    // cannot be sandboxed; the public adapter contract also requires one owner.
    for (const char *id : {"rezygisk", "ReZygisk", "neozygisk", "NeoZygisk", "zygisksu", "zygisk_next"}) {
        string dir = string("/data/adb/modules/") + id;
        if (access((dir + "/module.prop").c_str(), F_OK) == 0 &&
            access((dir + "/disable").c_str(), F_OK) != 0 &&
            access((dir + "/remove").c_str(), F_OK) != 0) return true;
    }
    return false;
}

bool is_sulist_enabled() { return inverse.load(); }
bool is_hide_ready() { return ready.load(); }

static bool read_selection(Selection &list, const char *table) {
    string sql = string("SELECT package_name,process FROM ") + table;
    return db_exec(sql.c_str(), {}, [&](StringSlice, const DbValues &values) {
        const char *pkg = values.get_text(0), *proc = values.get_text(1);
        if (hide::valid_pair(pkg, proc)) list.packages[pkg].emplace(proc);
    });
}

static void scan_apps(Selection &list) {
    list.uids.clear();
    // Missing or locked profiles are not evidence that a package was uninstalled.
    // Preserve selections; only an explicit remove changes the database.
    auto users = xopen_dir(APP_DATA_DIR);
    if (!users) return;
    for (dirent *user; (user = xreaddir(users.get()));) {
        if (parse_int(user->d_name) < 0) continue;
        int fd = openat(dirfd(users.get()), user->d_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (fd < 0) continue;
        for (const auto &[pkg, procs] : list.packages) {
            struct stat st{};
            if (fstatat(fd, pkg.c_str(), &st, AT_SYMLINK_NOFOLLOW) == 0 && S_ISDIR(st.st_mode))
                list.uids[st.st_uid].emplace(pkg);
        }
        close(fd);
    }
}

static bool ensure_data() {
    if (loaded) return true;
    Selection new_deny, new_allow;
    if (!read_selection(new_deny, "denylist") || !read_selection(new_allow, "sulist")) return false;
    deny = std::move(new_deny);
    allow = std::move(new_allow);
    scan_apps(deny);
    scan_apps(allow);
    loaded = true;
    return true;
}

void scan_deny_apps() {
    mutex_guard lock(data_lock);
    if (!ensure_data()) return;
    scan_apps(deny);
    scan_apps(allow);
}

// Call with data_lock held. No package names or decisions are cached across a
// package database replacement, including an install in a secondary profile.
static void refresh_packages(int uid) {
    static struct stat previous{};
    static map<int, struct stat> user_dirs;
    struct stat st{};
    bool changed = false;
    if (stat("/data/system/packages.xml", &st) == 0 &&
        (st.st_ino != previous.st_ino || st.st_mtime != previous.st_mtime ||
         st.st_mtim.tv_nsec != previous.st_mtim.tv_nsec ||
         st.st_size != previous.st_size || st.st_ctime != previous.st_ctime)) {
        changed = true;
        previous = st;
    }
    char path[PATH_MAX];
    int user = to_user_id(uid);
    ssprintf(path, sizeof(path), "%s/%d", APP_DATA_DIR, user);
    auto &last = user_dirs[user];
    if (stat(path, &st) == 0 && (last.st_ino != st.st_ino || last.st_mtime != st.st_mtime ||
        last.st_mtim.tv_nsec != st.st_mtim.tv_nsec)) {
        changed = true;
        last = st;
    }
    if (changed) { scan_apps(deny); scan_apps(allow); }
}

static bool selected(const Selection &list, int uid, string_view process) {
    int app = to_app_id(uid);
    string_view isolated_process = process;
    bool isolated = app >= 90000;
    if (!isolated && process.ends_with("_zygote")) {
        // App zygotes specialize under the owning app UID before forking their
        // isolated services. Select the parent too: its children inherit mounts
        // and do not pass through the main zygote's native bridge again.
        isolated_process.remove_suffix(strlen("_zygote"));
        auto pkg = isolated_process.substr(0, isolated_process.find(':'));
        char path[PATH_MAX];
        ssprintf(path, sizeof(path), "%s/%d/%.*s", APP_DATA_DIR, to_user_id(uid),
                 static_cast<int>(pkg.size()), pkg.data());
        struct stat st{};
        isolated = lstat(path, &st) == 0 && S_ISDIR(st.st_mode) && st.st_uid == static_cast<uid_t>(uid);
    }
    if (isolated) {
        auto it = list.packages.find(ISOLATED_MAGIC);
        if (it != list.packages.end())
            for (const auto &prefix : it->second)
                if (hide::isolated_match(isolated_process, prefix)) return true;
    }
    if (app == WEBVIEW_ZYGOTE_UID) {
        return list.packages.contains(WEBVIEW_ZYGOTE_MAGIC);
    } else if (auto it = list.uids.find(uid); it != list.uids.end()) {
        for (const auto &pkg : it->second)
            if (list.packages.find(pkg)->second.contains(process)) return true;
    }
    return false;
}

static bool automatic(int uid, string_view process) {
    // Never unmount the system server or the root/bootstrap domain. The manager
    // exception uses the verified installed manager UID, including hidden installs.
    if (uid == 0 || (to_app_id(uid) == 1000 && process == "system_server")) return true;
    if (MagiskD::Get().get_manager_uid(to_user_id(uid)) == uid) return true;
    return inverse && to_app_id(uid) == 1000 &&
        (process == "com.android.systemui" || process == "com.android.settings");
}

bool is_deny_target(int uid, string_view process) {
    if (uid < 0 || process.empty() || automatic(uid, process)) return false;
    mutex_guard lock(data_lock);
    // An unreadable selection must not expose unlisted apps in inverse mode.
    if (!ensure_data()) return inverse;
    refresh_packages(uid);
    return hide::unmount(inverse, selected(inverse ? allow : deny, uid, process), false);
}

bool sulist_allows_uid(int uid) {
    // ADB remains a recovery route, subject to the ordinary SU policy. Selection
    // never grants SU; it can only restrict the existing policy/prompt decision.
    if (!inverse || uid == 0 || uid == AID_SHELL || to_app_id(uid) == 1000 ||
        MagiskD::Get().get_manager_uid(to_user_id(uid)) == uid) return true;
    mutex_guard lock(data_lock);
    if (!ensure_data()) return false;
    refresh_packages(uid);
    return allow.uids.contains(uid);
}

bool proc_context_match(int pid, string_view context) {
    char path[64], con[256]{};
    ssprintf(path, sizeof(path), "/proc/%d/attr/current", pid);
    auto fp = open_file(path, "re");
    return fp && fgets(con, sizeof(con), fp.get()) &&
        string_view(con).substr(0, strcspn(con, "\n")) == context;
}

static void restart_selected(const Selection &list, string_view pkg, string_view process) {
    if (!denylist_enforced) return;
    auto proc = xopen_dir("/proc");
    if (!proc) return;
    for (dirent *entry; (entry = xreaddir(proc.get()));) {
        int pid = parse_int(entry->d_name);
        if (pid <= 1) continue;
        int pidfd = syscall(__NR_pidfd_open, pid, 0);
        if (pidfd < 0) continue; // Old kernels require an explicit app relaunch.
        run_finally pid_guard([&] { close(pidfd); });
        struct stat st{};
        if (fstatat(dirfd(proc.get()), entry->d_name, &st, 0) || st.st_uid < 10000) continue;
        char path[64], name[256]{};
        ssprintf(path, sizeof(path), "/proc/%d/cmdline", pid);
        auto fp = open_file(path, "re");
        if (!fp || !fgets(name, sizeof(name), fp.get())) continue;
        bool match = false;
        if (pkg == ISOLATED_MAGIC) {
            match = to_app_id(st.st_uid) >= 90000 && hide::isolated_match(name, process);
        } else if (auto it = list.uids.find(st.st_uid); it != list.uids.end()) {
            match = it->second.contains(string(pkg)) &&
                (process.empty() ? (name == pkg || string_view(name).starts_with(string(pkg) + ":"))
                                 : name == process);
        }
        if (match) syscall(__NR_pidfd_send_signal, pidfd, SIGKILL, nullptr, 0);
    }
}

int change_list(int client, bool remove, bool use_allow) {
    string pkg, proc;
    if (!read_string(client, pkg) || !read_string(client, proc)) return DenyResponse::ERROR;
    if (!remove && proc.empty()) proc = pkg;
    if (!hide::valid_pair(pkg, proc.empty() ? pkg : proc)) return DenyResponse::INVALID_PKG;
    mutex_guard lock(data_lock);
    if (!ensure_data()) return DenyResponse::ERROR;
    Selection &list = use_allow ? allow : deny;
    string table = use_allow ? "sulist" : "denylist";
    auto it = list.packages.find(pkg);
    bool exists = it != list.packages.end() && (proc.empty() || it->second.contains(proc));
    if (remove && !exists) return DenyResponse::ITEM_NOT_EXIST;
    if (!remove && exists) return DenyResponse::ITEM_EXIST;
    string sql = remove ? "DELETE FROM " + table + " WHERE package_name=?" :
                         "INSERT INTO " + table + "(package_name,process) VALUES(?,?)";
    if (remove && !proc.empty()) sql += " AND process=?";
    if (!db_exec(sql.c_str(), {pkg.c_str(), proc.c_str()})) return DenyResponse::ERROR;
    // Publish only a committed write. Kill only affected app processes, including
    // all profiles; never system_server, a zygote or a same-named different UID.
    scan_apps(list);
    restart_selected(list, pkg, proc);
    if (remove) {
        if (proc.empty()) list.packages.erase(pkg);
        else {
            it->second.erase(proc);
            if (it->second.empty()) list.packages.erase(it);
        }
    } else {
        list.packages[pkg].emplace(proc);
    }
    scan_apps(list);
    if (!remove) restart_selected(list, pkg, proc);
    return DenyResponse::OK;
}

void list_selection(int client, bool use_allow) {
    mutex_guard lock(data_lock);
    if (!ensure_data()) {
        write_int(client, static_cast<int>(DenyResponse::ERROR));
        close(client);
        return;
    }
    write_int(client, static_cast<int>(DenyResponse::OK));
    for (const auto &[pkg, procs] : (use_allow ? allow : deny).packages)
        for (const auto &proc : procs) write_string(client, pkg + "|" + proc);
    write_int(client, 0);
    close(client);
}

int add_list(int client) { return change_list(client, false, false); }
int rm_list(int client) { return change_list(client, true, false); }
void ls_list(int client) { list_selection(client, false); }

int enable_deny() {
    mutex_guard lock(data_lock);
    if (hide_enabled) return DenyResponse::OK;
    if (external_owner) {
        if (MagiskD::Get().zygisk_enabled() || !external_adapter_installed())
            return DenyResponse::UNSUPPORTED_PROVIDER;
    } else if (external_at_boot || external_provider_installed()) {
        return DenyResponse::UNSUPPORTED_PROVIDER;
    }
    if (access("/proc/self/ns/mnt", F_OK)) return DenyResponse::NO_NS;
    if (!ensure_data()) return DenyResponse::ERROR;
    if (!external_owner && !MagiskD::Get().zygisk_enabled() && !start_hide_monitor())
        return DenyResponse::ERROR;
    if (!db_exec("REPLACE INTO settings(key,value) VALUES('denylist',1),('magiskhide',1)"))
        return DenyResponse::ERROR;
    denylist_enforced = !external_owner;
    hide_enabled = true;
    LOGI("* Enable %s\n", inverse ? "SuList" : "MagiskHide");
    return DenyResponse::OK;
}

int disable_deny() {
    mutex_guard lock(data_lock);
    if (inverse) return DenyResponse::REBOOT_REQUIRED;
    if (!db_exec("REPLACE INTO settings(key,value) VALUES('denylist',0),('magiskhide',0)"))
        return DenyResponse::ERROR;
    denylist_enforced = false;
    hide_enabled = false;
    return DenyResponse::OK;
}

int set_hide_mode(bool sulist) {
    mutex_guard lock(data_lock);
    if (sulist && (external_at_boot || external_provider_installed()) &&
        !(external_owner && external_adapter_installed()))
        return DenyResponse::UNSUPPORTED_PROVIDER;
    if (!db_exec(sulist ?
            "REPLACE INTO settings(key,value) VALUES('sulist',1)" :
            "REPLACE INTO settings(key,value) VALUES('sulist',0)")) return DenyResponse::ERROR;
    return DenyResponse::OK;
}

int set_hide_provider(bool external) {
    mutex_guard lock(data_lock);
    if (external && (!external_adapter_installed() ||
        MagiskD::Get().get_db_setting(DbEntryKey::ZygiskConfig)))
        return DenyResponse::UNSUPPORTED_PROVIDER;
    return db_exec("REPLACE INTO settings(key,value) VALUES('hide_provider',?)", {int64_t(external)})
        ? DenyResponse::OK : DenyResponse::ERROR;
}

void initialize_denylist() {
    external_at_boot = external_provider_installed();
    bool enable = false, mode = false;
    if (!db_exec("SELECT key,value FROM settings WHERE key IN ('denylist','sulist','hide_provider')", {},
            [&](StringSlice, const DbValues &v) {
                if (string_view(v.get_text(0)) == "sulist") mode = v.get_int(1) != 0;
                else if (string_view(v.get_text(0)) == "hide_provider") external_owner = v.get_int(1) == 1;
                else enable = v.get_int(1) != 0;
            })) return;
    inverse = mode;
    if ((enable || mode) && enable_deny() != DenyResponse::OK) {
        LOGE("hide: enforcement unavailable\n");
        // Keep inverse latched: SU must remain restricted even if monitoring fails.
    }
    ready = true;
}

void update_deny_flags(int uid, rust::Str process, uint32_t &flags) {
    if (is_deny_target(uid, {process.begin(), process.end()}))
        flags |= +ZygiskStateFlags::ProcessOnDenyList;
    if (denylist_enforced || inverse) flags |= +ZygiskStateFlags::DenyListEnforced;
}

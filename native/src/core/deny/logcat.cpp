#include <unistd.h>
#include <android/log.h>
#include <sys/syscall.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <string>
#include <map>

#include <core.hpp>

#include "deny.hpp"

using namespace std;

struct logger_entry {
    uint16_t len;      /* length of the payload */
    uint16_t hdr_size; /* sizeof(struct logger_entry) */
    int32_t pid;       /* generating process's pid */
    uint32_t tid;      /* generating process's tid */
    uint32_t sec;      /* seconds since Epoch */
    uint32_t nsec;     /* nanoseconds */
    uint32_t lid;      /* log id of the payload, bottom 4 bits currently */
    uint32_t uid;      /* generating process's uid */
};

#define LOGGER_ENTRY_MAX_LEN (5 * 1024)
struct log_msg {
    union [[gnu::aligned(4)]] {
        unsigned char buf[LOGGER_ENTRY_MAX_LEN + 1];
        struct logger_entry entry;
    };
};

struct AndroidLogEntry {
    time_t tv_sec;
    long tv_nsec;
    android_LogPriority priority;
    int32_t uid;
    int32_t pid;
    int32_t tid;
    const char *tag;
    size_t tagLen;
    size_t messageLen;
    const char *message;
};

struct [[gnu::packed]] android_event_header_t {
    int32_t tag;    // Little Endian Order
};

struct [[gnu::packed]] android_event_int_t {
    int8_t type;    // EVENT_TYPE_INT
    int32_t data;   // Little Endian Order
};

struct [[gnu::packed]] android_event_string_t {
    int8_t type;    // EVENT_TYPE_STRING;
    int32_t length; // Little Endian Order
    char data[];
};

struct [[gnu::packed]] android_event_list_t {
    int8_t type;    // EVENT_TYPE_LIST
    int8_t element_count;
} ;

// 30014 am_proc_start (User|1|5),(PID|1|5),(UID|1|5),(Process Name|3),(Type|3),(Component|3)
struct [[gnu::packed]] android_event_am_proc_start {
    android_event_header_t tag;
    android_event_list_t list;
    android_event_int_t user;
    android_event_int_t pid;
    android_event_int_t uid;
    android_event_string_t process_name;
//  android_event_string_t type;
//  android_event_string_t component;
};

// 3040 boot_progress_ams_ready (time|2|3)

extern "C" {

[[gnu::weak]] struct logger_list *android_logger_list_alloc(int mode, unsigned int tail, pid_t pid);
[[gnu::weak]] void android_logger_list_free(struct logger_list *list);
[[gnu::weak]] int android_logger_list_read(struct logger_list *list, struct log_msg *log_msg);
[[gnu::weak]] struct logger *android_logger_open(struct logger_list *list, log_id_t id);
[[gnu::weak]] int android_log_processLogBuffer(struct logger_entry *buf, AndroidLogEntry *entry);

}


// One reader for the daemon lifetime. Disabling enforcement leaves it dormant;
// re-enabling never creates another blocked logd reader or a duplicate worker.
static atomic<bool> monitor_started = false;
static map<int, struct stat> zygotes;

static sFILE open_file_at(int dir, const char *path, const char *mode) {
    int fd = openat(dir, path, O_RDONLY | O_CLOEXEC);
    FILE *fp = fd < 0 ? nullptr : fdopen(fd, mode);
    if (!fp && fd >= 0) close(fd);
    return make_file(fp);
}

static int parent_pid(int proc) {
    auto fp = open_file_at(proc, "stat", "re");
    if (!fp) return -1;
    char line[4096]{};
    if (!fgets(line, sizeof(line), fp.get())) return -1;
    // comm may contain spaces or ')'; PPID starts after the final ') STATE '.
    char *end = strrchr(line, ')');
    int ppid = -1;
    if (end) sscanf(end + 1, " %*c %d", &ppid);
    return ppid;
}

static bool zygote_identity(int pid, int proc) {
    struct stat st{};
    if (fstat(proc, &st) || st.st_uid != 0 || parent_pid(proc) != 1) return false;
    char name[128]{};
    auto fp = open_file_at(proc, "cmdline", "re");
    if (!fp || !fgets(name, sizeof(name), fp.get())) return false;
    if (strcmp(name, "zygote") && strcmp(name, "zygote64") && strcmp(name, "zygote32")) return false;
    if (!selinux_disabled()) return proc_context_match(pid, "u:r:zygote:s0");
    char exe[PATH_MAX]{};
    ssize_t len = readlinkat(proc, "exe", exe, sizeof(exe) - 1);
    if (len <= 0) return false;
    exe[len] = '\0';
    return string_view(exe).starts_with("/system/bin/app_process") ||
           string_view(exe).starts_with("/apex/com.android.art/bin/app_process");
}

static void check_zygote() {
    zygotes.clear();
    auto proc = xopen_dir("/proc");
    if (!proc) return;
    for (dirent *entry; (entry = xreaddir(proc.get()));) {
        int pid = parse_int(entry->d_name);
        if (pid <= 1) continue;
        int fd = openat(dirfd(proc.get()), entry->d_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (fd < 0) continue;
        struct stat st{};
        if (zygote_identity(pid, fd) && fstatat(fd, "ns/mnt", &st, 0) == 0) zygotes[pid] = st;
        close(fd);
    }
}

static void clean_process(int pid, int uid, string_view name, bool app_zygote = false) {
    if (!denylist_enforced || pid <= 1 || !is_deny_target(uid, name)) return;
    char path[64];
    ssprintf(path, sizeof(path), "/proc/%d", pid);
    int proc = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (proc < 0) return;
    // An open proc directory anchors the process, even if its numeric PID is reused.
    int ppid = parent_pid(proc);
    if (!zygotes.contains(ppid)) check_zygote();
    auto parent = zygotes.find(ppid);
    if (parent == zygotes.end()) { LOGD("hide: parent not verified\n"); close(proc); return; }
    ssprintf(path, sizeof(path), "/proc/%d", ppid);
    int parent_proc = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    struct stat parent_ns{}, init_ns{};
    bool trusted = parent_proc >= 0 && zygote_identity(ppid, parent_proc) &&
        fstatat(parent_proc, "ns/mnt", &parent_ns, 0) == 0 && stat("/proc/1/ns/mnt", &init_ns) == 0;
    if (parent_proc >= 0) close(parent_proc);
    if (!trusted) { close(proc); return; }
    int fd = -1;
    // ActivityManager can publish am_proc_start before specialization finishes.
    // Wait for both the requested identity and a private namespace, with a hard
    // deadline. The proc directory stays open throughout, so PID reuse is safe.
    for (int attempt = 0; attempt < 100; ++attempt) {
        struct stat st{}, ns{};
        char command[1025]{};
        auto fp = open_file_at(proc, "cmdline", "re");
        if (!fp || fstat(proc, &st) || parent_pid(proc) != ppid) break;
        if (fgets(command, sizeof(command), fp.get()) && name == command &&
            st.st_uid == static_cast<uid_t>(uid) &&
            (!app_zygote || selinux_disabled() || proc_context_match(pid, "u:r:app_zygote:s0"))) {
            fd = openat(proc, "ns/mnt", O_RDONLY | O_CLOEXEC);
            if (fd >= 0 && fstat(fd, &ns) == 0 &&
                (ns.st_ino != parent_ns.st_ino || ns.st_dev != parent_ns.st_dev) &&
                (ns.st_ino != init_ns.st_ino || ns.st_dev != init_ns.st_dev)) break;
            if (fd >= 0) close(fd);
            fd = -1;
        }
        usleep(2000);
    }
    close(proc);
    if (fd < 0) { LOGD("hide: specialization deadline exceeded\n"); return; }
    if (!denylist_enforced || !is_deny_target(uid, name)) { close(fd); return; }
    // Never stop app threads: failure to fork, switch namespaces or unmount must
    // not leave a SIGSTOP'ed app behind. The log engine is asynchronous by design.
    if (fork_dont_care() == 0) {
        if (setns(fd, CLONE_NEWNS) == 0 &&
            mount(nullptr, "/", nullptr, MS_PRIVATE | MS_REC, nullptr) == 0) revert_unmount();
        else PLOGE("hide: namespace cleanup");
        _exit(0);
    }
    close(fd);
}

static void process_events_buffer(const log_msg &msg, size_t size) {
    if (msg.entry.uid != 1000 || size < sizeof(android_event_header_t)) return;
    const auto *data = msg.buf + msg.entry.hdr_size;
    int32_t tag;
    memcpy(&tag, data, sizeof(tag));
    if (tag == 3040) { check_zygote(); scan_deny_apps(); return; }
    if (tag != 30014 || size < sizeof(android_event_am_proc_start)) return;
    const auto *event = reinterpret_cast<const android_event_am_proc_start *>(data);
    if (event->list.type != 3 || event->list.element_count < 4 ||
        event->user.type != 0 || event->pid.type != 0 || event->uid.type != 0 ||
        event->process_name.type != 2) return;
    int length = event->process_name.length;
    if (length <= 0 || length > 1024 ||
        static_cast<size_t>(length) > size - sizeof(android_event_am_proc_start)) return;
    string_view name(event->process_name.data, length);
    if (name.find('\0') != string_view::npos) return;
    clean_process(event->pid.data, event->uid.data, name);
}

static void process_main_buffer(log_msg &msg) {
    AndroidLogEntry entry{};
    if (android_log_processLogBuffer(&msg.entry, &entry) < 0 || entry.tagLen == 0) return;
    string_view tag(entry.tag, strnlen(entry.tag, entry.tagLen));
    if (tag != "AppZygoteInit" && tag != "WebViewZygoteInit") return;
    if (tag == "WebViewZygoteInit" && entry.uid != WEBVIEW_ZYGOTE_UID) return;
    char path[64], name[1025]{};
    ssprintf(path, sizeof(path), "/proc/%d/cmdline", msg.entry.pid);
    auto fp = open_file(path, "re");
    if (fp && fgets(name, sizeof(name), fp.get()))
        clean_process(msg.entry.pid, entry.uid, name, tag == "AppZygoteInit");
}

void *logcat(void *) {
    check_zygote();
    for (;;) {
        const unique_ptr<logger_list, decltype(&android_logger_list_free)> reader{
            android_logger_list_alloc(0, 1, 0), &android_logger_list_free};
        if (!reader) { sleep(1); continue; }
        android_logger_open(reader.get(), LOG_ID_MAIN);
        android_logger_open(reader.get(), LOG_ID_EVENTS);
        log_msg msg{};
        int bytes;
        while ((bytes = android_logger_list_read(reader.get(), &msg)) > 0) {
            if (!denylist_enforced || msg.entry.hdr_size < sizeof(logger_entry) ||
                msg.entry.hdr_size > bytes || msg.entry.len > bytes - msg.entry.hdr_size ||
                static_cast<size_t>(bytes) > sizeof(msg.buf)) continue;
            if (msg.entry.lid == LOG_ID_EVENTS) process_events_buffer(msg, msg.entry.len);
            else if (msg.entry.lid == LOG_ID_MAIN) process_main_buffer(msg);
        }
        LOGD("hide: log reader reconnect (%d)\n", bytes);
        sleep(1);
    }
}

bool start_hide_monitor() {
    if (monitor_started) return true;
    if (!android_logger_list_alloc || !android_logger_list_free || !android_logger_list_read ||
        !android_logger_open || !android_log_processLogBuffer) return false;
    if (monitor_started.exchange(true)) return true;
    if (new_daemon_thread(&logcat)) { monitor_started = false; return false; }
    return true;
}

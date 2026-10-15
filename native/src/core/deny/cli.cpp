#include <sys/wait.h>
#include <sys/mount.h>

#include <core.hpp>
#include <sqlite.hpp>

#include "deny.hpp"
#include "policy.hpp"

using namespace std;

[[noreturn]] static void usage() {
    fprintf(stderr,
R"EOF(DenyList Config CLI

Usage: magisk --denylist [action [arguments...] ]
Actions:
   status          Return the enforcement status
   enable          Enable denylist enforcement
   disable         Disable denylist enforcement
   add PKG [PROC]  Add a new target to the denylist
   rm PKG [PROC]   Remove target(s) from the denylist
   ls              Print the current denylist
   exec CMDs...    Execute commands in isolated mount
                   namespace and do all unmounts

)EOF");
    exit(1);
}

void denylist_handler(int client) {
    if (client < 0) {
        revert_unmount();
        return;
    }

    int req = read_int(client);
    int res = DenyResponse::ERROR;

    switch (req) {
    case DenyRequest::ENFORCE:
        res = enable_deny();
        break;
    case DenyRequest::DISABLE:
        res = disable_deny();
        break;
    case DenyRequest::ADD:
        res = add_list(client);
        break;
    case DenyRequest::REMOVE:
        res = rm_list(client);
        break;
    case DenyRequest::LIST:
        ls_list(client);
        return;
    case DenyRequest::STATUS:
        res = denylist_enforced ? DenyResponse::ENFORCED : DenyResponse::NOT_ENFORCED;
        break;
    default:
        // Unknown request code
        break;
    }
    write_int(client, res);
    close(client);
}

int denylist_cli(rust::Vec<rust::String> &args) {
    if (args.empty())
        usage();

    // Convert rust strings into c strings
    size_t argc = args.size();
    std::vector<const char *> argv;
    ranges::transform(args, std::back_inserter(argv), [](rust::String &arg) { return arg.c_str(); });
    // End with nullptr
    argv.push_back(nullptr);

    int req;
    if (argv[0] == "enable"sv)
        req = DenyRequest::ENFORCE;
    else if (argv[0] == "disable"sv)
        req = DenyRequest::DISABLE;
    else if (argv[0] == "add"sv)
        req = DenyRequest::ADD;
    else if (argv[0] == "rm"sv)
        req = DenyRequest::REMOVE;
    else if (argv[0] == "ls"sv)
        req = DenyRequest::LIST;
    else if (argv[0] == "status"sv)
        req = DenyRequest::STATUS;
    else if (argv[0] == "exec"sv && argc > 1) {
        if (unshare(CLONE_NEWNS) || mount(nullptr, "/", nullptr, MS_PRIVATE | MS_REC, nullptr))
            return 1;
        revert_unmount();
        execvp(argv[1], (char **) argv.data() + 1);
        exit(1);
    } else {
        usage();
    }

    if ((req == DenyRequest::ADD || req == DenyRequest::REMOVE) &&
        (argc < 2 || argc > 3))
        usage();
    if (req != DenyRequest::ADD && req != DenyRequest::REMOVE && argc != 1)
        usage();

    // Send request
    int fd = connect_daemon(RequestCode::DENYLIST);
    if (fd < 0)
        return 1;
    write_int(fd, req);
    if (req == DenyRequest::ADD || req == DenyRequest::REMOVE) {
        write_string(fd, argv[1]);
        write_string(fd, argv[2] ? argv[2] : "");
    }

    // Get response
    int res = read_int(fd);
    if (res < 0 || res >= DenyResponse::END)
        res = DenyResponse::ERROR;
    switch (res) {
    case DenyResponse::NOT_ENFORCED:
        fprintf(stderr, "Denylist is not enforced\n");
        goto return_code;
    case DenyResponse::ENFORCED:
        fprintf(stderr, "Denylist is enforced\n");
        goto return_code;
    case DenyResponse::ITEM_EXIST:
        fprintf(stderr, "Target already exists in denylist\n");
        goto return_code;
    case DenyResponse::ITEM_NOT_EXIST:
        fprintf(stderr, "Target does not exist in denylist\n");
        goto return_code;
    case DenyResponse::NO_NS:
        fprintf(stderr, "The kernel does not support mount namespace\n");
        goto return_code;
    case DenyResponse::INVALID_PKG:
        fprintf(stderr, "Invalid package / process name\n");
        goto return_code;
    case DenyResponse::ERROR:
        fprintf(stderr, "deny: Daemon error\n");
        return -1;
    case DenyResponse::REBOOT_REQUIRED:
        fprintf(stderr, "SuList is active; select hide mode and cold boot first\n");
        goto return_code;
    case DenyResponse::UNSUPPORTED_PROVIDER:
        fprintf(stderr, "External provider has no Hide/SuList adapter; disable it and cold boot first\n");
        goto return_code;
    case DenyResponse::OK:
        break;
    default:
        __builtin_unreachable();
    }

    if (req == DenyRequest::LIST) {
        string out;
        for (;;) {
            read_string(fd, out);
            if (out.empty())
                break;
            printf("%s\n", out.data());
        }
    }

return_code:
    close(fd);
    return req == DenyRequest::STATUS ? res != DenyResponse::ENFORCED : res != DenyResponse::OK;
}

// The upstream request and table remain a negative list. Kitsune extensions use
// their own authenticated request ID so old daemons cannot misinterpret them.
void hide_handler(int client) {
    int req = read_int(client);
    int res = DenyResponse::ERROR;
    switch (req) {
    case DenyRequest::STATUS: {
        int configured = 0, provider = 0;
        if (!db_exec("SELECT key,value FROM settings WHERE key IN ('sulist','hide_provider')", {},
                [&](StringSlice, const DbValues &v) {
                    if (string_view(v.get_text(0)) == "sulist") configured = v.get_int(1) != 0;
                    else provider = v.get_int(1) == 1;
                })) break;
        const char *mode = is_sulist_enabled() ? "sulist" : "hide";
        char out[768];
        ssprintf(out, sizeof(out),
            "{\"schema\":1,\"database_version\":12,\"boot_ready\":%s,\"enabled\":%s,"
            "\"mode\":\"%s\",\"configured_mode\":\"%s\",\"reboot_required\":%s,"
            "\"selection_table\":\"%s\",\"engine\":\"%s\",\"configured_provider\":\"%s\","
            "\"external_sulist_supported\":%s}",
            is_hide_ready() ? "true" : "false", is_hide_enabled() ? "true" : "false", mode,
            configured ? "sulist" : "hide",
            configured != is_sulist_enabled() || provider != is_external_hide() ? "true" : "false",
            is_sulist_enabled() ? "sulist" : "denylist",
            is_external_hide() ? "external" : (MagiskD::Get().zygisk_enabled() ? "builtin" : "logcat"),
            provider ? "external" : "core", is_external_hide() ? "true" : "false");
        write_int(client, static_cast<int>(DenyResponse::OK));
        write_string(client, out);
        close(client);
        return;
    }
    case DenyRequest::MODE: {
        int mode = read_int(client);
        if (mode == 0 || mode == 1) res = set_hide_mode(mode);
        break;
    }
    case DenyRequest::PROVIDER: {
        int provider = read_int(client);
        if (provider == 0 || provider == 1) res = set_hide_provider(provider);
        break;
    }
    case DenyRequest::CHECK: {
        int uid = read_int(client);
        string process;
        if (uid < 0 || !read_string(client, process) || !hide::valid_name(process, true)) break;
        bool unmount = (is_hide_enabled() || is_sulist_enabled()) && is_deny_target(uid, process);
        write_int(client, static_cast<int>(DenyResponse::OK));
        string out = string("{\"schema\":1,\"unmount\":") + (unmount ? "true" : "false") +
            ",\"su_eligible\":" + (sulist_allows_uid(uid) ? "true" : "false") +
            ",\"manager\":" + (MagiskD::Get().get_manager_uid(to_user_id(uid)) == uid ? "true" : "false") + "}";
        write_string(client, out);
        close(client);
        return;
    }
    case DenyRequest::ENFORCE: res = enable_deny(); break;
    case DenyRequest::DISABLE: res = disable_deny(); break;
    case DenyRequest::ADD: res = change_list(client, false, is_sulist_enabled()); break;
    case DenyRequest::REMOVE: res = change_list(client, true, is_sulist_enabled()); break;
    case DenyRequest::LIST: list_selection(client, is_sulist_enabled()); return;
    }
    write_int(client, res);
    close(client);
}

int hide_cli(rust::Vec<rust::String> &args) {
    auto usage = [] {
        fprintf(stderr,
            "Usage: magisk --hide status|enable|disable|ls\n"
            "       magisk --hide add|rm PKG [PROCESS]\n"
            "       magisk --hide mode hide|sulist   (next boot)\n"
            "       magisk --hide provider core|external   (next boot)\n"
            "       magisk --hide check UID PROCESS\n"
            "       magisk --hide exec COMMAND [ARG...]\n");
        return 2;
    };
    if (args.empty()) return usage();
    string_view action(args[0].c_str());
    int req = -1, mode = -1, uid = -1;
    if (action == "exec") {
        if (args.size() < 2) return usage();
        // Never unmount the caller's namespace if isolation or propagation fails.
        if (unshare(CLONE_NEWNS) || mount(nullptr, "/", nullptr, MS_PRIVATE | MS_REC, nullptr)) return 1;
        revert_unmount();
        vector<char *> argv;
        for (size_t i = 1; i < args.size(); ++i) argv.push_back(const_cast<char *>(args[i].c_str()));
        argv.push_back(nullptr);
        execvp(argv[0], argv.data());
        return errno == ENOENT ? 127 : 126;
    }
    if (action == "provider") {
        if (args.size() != 2) return usage();
        string_view value(args[1].c_str());
        if (value != "core" && value != "external") return usage();
        req = DenyRequest::PROVIDER;
        mode = value == "external";
    } else if (action == "mode" || action == "sulist") {
        if (action == "sulist" && args.size() == 1) req = DenyRequest::STATUS;
        else {
            if (args.size() != 2) return usage();
            string_view value(args[1].c_str());
            if (value == "sulist" || (action == "sulist" && value == "enable")) mode = 1;
            else if (value == "hide" || (action == "sulist" && value == "disable")) mode = 0;
            else return usage();
            req = DenyRequest::MODE;
        }
    } else if (action == "add" || action == "rm") {
        if (args.size() < 2 || args.size() > 3) return usage();
        req = action == "add" ? DenyRequest::ADD : DenyRequest::REMOVE;
    } else if (action == "check") {
        if (args.size() != 3 || (uid = parse_int(args[1].c_str())) < 0) return usage();
        req = DenyRequest::CHECK;
    } else {
        if (args.size() != 1) return usage();
        if (action == "status") req = DenyRequest::STATUS;
        else if (action == "enable") req = DenyRequest::ENFORCE;
        else if (action == "disable") req = DenyRequest::DISABLE;
        else if (action == "ls") req = DenyRequest::LIST;
        else return usage();
    }
    int fd = connect_daemon(RequestCode::HIDE);
    if (fd < 0) return 1;
    write_int(fd, req);
    if (req == DenyRequest::MODE || req == DenyRequest::PROVIDER) write_int(fd, mode);
    if (req == DenyRequest::CHECK) { write_int(fd, uid); write_string(fd, args[2].c_str()); }
    if (req == DenyRequest::ADD || req == DenyRequest::REMOVE) {
        write_string(fd, args[1].c_str());
        write_string(fd, args.size() == 3 ? args[2].c_str() : "");
    }
    int res = read_int(fd);
    if (res < 0 || res >= DenyResponse::END) res = DenyResponse::ERROR;
    if (res == DenyResponse::OK) {
        if (req == DenyRequest::LIST) {
            string row;
            while (read_string(fd, row) && !row.empty()) printf("%s\n", row.c_str());
        } else if (req == DenyRequest::STATUS || req == DenyRequest::CHECK) {
            string out;
            if (!read_string(fd, out) || out.empty()) res = DenyResponse::ERROR;
            else printf("%s\n", out.c_str());
        }
    }
    close(fd);
    if (res != DenyResponse::OK ||
        (req != DenyRequest::STATUS && req != DenyRequest::CHECK && req != DenyRequest::LIST))
        printf("{\"schema\":1,\"code\":%d}\n", res);
    return res;
}

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include "api.hpp"

extern "C" [[gnu::visibility("default"), gnu::used]]
const char kitsune_zygisk_probe_contract[] = "kitsune-zygisk-test-v1:api5-companion";

static constexpr unsigned reply_magic = 0x4b5a5031;

static void companion(int fd) {
    unsigned reply = getuid() == 0 ? reply_magic : 0;
    // A bounded reply only; the test companion never accepts commands or paths.
    while (send(fd, &reply, sizeof(reply), MSG_NOSIGNAL) < 0 && errno == EINTR) {}
}

class ProbeModule final : public zygisk::ModuleBase {
    zygisk::Api *api = nullptr;
    JNIEnv *env = nullptr;
    bool target = false;

public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override {
        this->api = api;
        this->env = env;
    }

    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        const char *name = env->GetStringUTFChars(args->nice_name, nullptr);
        if (!name) return;
        target = strcmp(name, KITSUNE_TEST_PACKAGE) == 0;
        env->ReleaseStringUTFChars(args->nice_name, name);
        if (!target) return;

        char flags[16];
        snprintf(flags, sizeof(flags), "%u", api->getFlags());
        setenv("KITSUNE_ZYGISK_FLAGS", flags, 1);

        int dir = api->getModuleDir();
        struct stat st{};
        bool directory = dir >= 0 && fstat(dir, &st) == 0 && S_ISDIR(st.st_mode);
        if (dir >= 0) close(dir);

        unsigned reply = 0;
        int fd = api->connectCompanion();
        if (fd >= 0) {
            timeval timeout{5, 0};
            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
            ssize_t size;
            do {
                size = recv(fd, &reply, sizeof(reply), MSG_WAITALL);
            } while (size < 0 && errno == EINTR);
            if (size != sizeof(reply)) reply = 0;
            close(fd);
        }
        setenv("KITSUNE_ZYGISK_PROBE", directory && reply == reply_magic ? "ok" : "failed", 1);
    }

    void postAppSpecialize(const zygisk::AppSpecializeArgs *) override {
        if (target) setenv("KITSUNE_ZYGISK_POST", "ok", 1);
    }
};

REGISTER_ZYGISK_MODULE(ProbeModule)
REGISTER_ZYGISK_COMPANION(companion)

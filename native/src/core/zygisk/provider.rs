use crate::daemon::MagiskD;
use crate::ffi::{is_denylist_enforced, is_sulist_enabled};
use crate::socket::IpcWrite;
use base::{LoggedResult, ResultExt};
use std::os::unix::net::UnixStream;
use std::sync::atomic::Ordering;

impl MagiskD {
    pub fn zygisk_status(&self, mut client: UnixStream) -> LoggedResult<()> {
        // Module scripts can query this during post-fs-data. Never wait on the boot-stage
        // lock here: the boot thread may itself be waiting for the querying script.
        let settings = self.get_db_settings().log()?;
        let boot_ready = self.module_list.get().is_some();
        let enabled = self.zygisk_enabled.load(Ordering::Acquire);
        let injection = !self.zygisk.lock().lib_name.is_empty();
        let enforced = is_denylist_enforced();
        let external = boot_ready
            && !settings.zygisk
            && !enabled
            && !injection
            && !enforced
            && !is_sulist_enabled()
            && !settings.sulist;

        // These are daemon observations, not proof that any app or external provider injected.
        // Keep the module API synchronized with api.hpp; the contract test pins that boundary.
        let status = format!(
            concat!(
                "{{\"schema\":1,\"model\":\"single-provider\",\"module_api\":5,",
                "\"boot_ready\":{},\"builtin_configured\":{},\"builtin_enabled\":{},",
                "\"injection_requested\":{},\"denylist_enforced\":{},",
                "\"external_preconditions_met\":{},\"hide_supported\":true,",
                "\"sulist_supported\":true}}"
            ),
            boot_ready, settings.zygisk, enabled, injection, enforced, external
        );
        client.write_encodable(&status).log()
    }
}

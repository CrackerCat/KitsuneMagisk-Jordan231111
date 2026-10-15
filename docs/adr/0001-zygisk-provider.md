# ADR 0001: one Zygisk provider per boot

PR11 retains the maintained Magisk built-in implementation and an explicit opt-out for
external providers. The same APK supports both configurations; there is no second core or
build flavor. Root, ordinary installation, managed System Mode, and recovery do not require
Zygisk. This decision replaces the historical blanket deletion of built-in Zygisk.

## Contract and ownership

The core owns root authorization, manager identity, module mounting, boot recovery and the
canonical `denylist(package_name, process)` selection. A selected injection provider owns
Zygisk callbacks, module loading and companion IPC. Exactly one engine may inject a process.
Built-in DenyList enforcement and an external provider's unmount engine must not run together.
Installing an external module never silently changes the core's settings or enables SuList.

The maintained built-in implementation is the supported baseline. External providers are
optional, independently installed root modules. Each release needs its own evidence; a
provider's name, running daemon, or successful module download is not a compatibility result.
The comparison pins are in [the PR11 evidence](../zygisk-pr11.json). Neither provider nor its
binary is vendored in Kitsune.

To use an external provider, disable built-in Zygisk and DenyList enforcement, disable/remove
any other external provider, and cold boot before relying on that provider. On MuMu, close and
open the exact instance through its CLI. To return to built-in, disable/remove the external
module and its installed service according to its uninstaller, enable built-in, and cold boot.
Do not switch providers inside a running zygote. Safe mode/remove-modules and stock or verified
external restoration remain the recovery routes.

### Read-only version 1 adapter boundary

`magisk --features` advertises `kitsune.zygisk-provider.v1` for the **binary**.
Root can query `magisk --zygisk-status` for the **running daemon**. It does not start a daemon.
The daemon authenticates peer credentials and rejects unprivileged requests. Its reserved
request ID is `0x4b490002`, outside the upstream request range, so an old daemon refuses the
request rather than interpreting it as another privileged operation. The existing module
API and internal Zygisk socket protocol are unchanged.

The response is one JSON object:

| Field | Meaning |
|---|---|
| `schema` | Integer `1`; reject unknown versions, missing fields, malformed JSON or failed commands. |
| `model` | `single-provider`. |
| `module_api` | Built-in maximum module API, currently `5`. This is independent of the manager protocol and Android version. |
| `boot_ready` | The daemon has finished selecting and applying modules for this boot. False during module scripts and safe mode. |
| `builtin_configured` | Persisted choice for the next boot. |
| `builtin_enabled` | Built-in choice latched by this daemon during post-fs-data. |
| `injection_requested` | The core currently owns a native-bridge injection request. This is not proof of injection into every process. |
| `denylist_enforced` | Live core enforcement, not merely the saved setting. |
| `external_preconditions_met` | Boot ready, with all three built-in fields false and core DenyList enforcement off. This does not detect or authenticate external modules. |
| `hide_supported`, `sulist_supported` | Both false on the PR11 core. PR12 owns those semantics; a legacy database key does not enable them. |

All boolean fields are JSON booleans. The response is an observation, not an authorization
token, atomic provider-switch operation, process-injection attestation, or external health
check. Root can change configuration immediately after a query. Boot scripts must tolerate
`boot_ready=false` without waiting for boot completion inside post-fs-data; otherwise they
would block the very stage they are waiting on. Database read failure fails the command.

Adapters must obtain the application ID from `--daemon-version-json`, not from the lowercase
`kitsune` compatibility marker. A hidden manager is resolved using the existing `strings`
`requester` contract; never fabricate a requester row for the normal APK. Manager UID and
signer authorization remain the core's responsibility. The CLI does not grant an external
provider access to the privileged Zygisk socket or bypass manager certificate checks.

`denylist` is a negative process selection. External versions that query only package names
cannot claim process-level parity. Do not invert the table into an allowlist, read old
`hidelist`/`sulist` tables as current authority, or infer SuList from a version number.
PR12 will version any changed Hide/SuList semantics and test the one-owner namespace boundary.

## Compatibility and threat model

Retaining the maintained loader avoids coupling recoverable root to third-party release
cadence and preserves ordinary Magisk API v5, module validation, companion IPC, Riru exclusion,
and safe-mode behavior. External root modules already have broad privileges; no provider
diagnostic can sandbox a malicious module. The boundary protects against accidental dual
injection, stale settings, incorrect manager discovery, and overstated compatibility.

The historical GrapheneOS Android 14 and QPR2 JNI descriptors from `ed27581a` and `3f2e5b42`
are restored alongside upstream descriptors. Their extra `long[]` is forwarded unchanged.
Frozen descriptor/argument-order tests and four-ABI compilation protect the port. They do not
qualify a physical GrapheneOS device; the PR15 physical-device gate remains explicit.

SELinux-enforcing, permissive and disabled targets are separate cases. This PR never disables
SELinux to make a provider pass. A permissive MuMu result cannot qualify enforcing phones or
SELinux-disabled/Waydroid targets. An unsupported security mode must stay unclaimed.

## Historical decisions

| Ledger row | Decision and affected-user migration |
|---|---|
| ZYG-001 | Retain API v5, validated module/memfd loading, companion IPC and Riru exclusion. Hide integration is the separately owned PR12 behavior, not an implied API property. |
| ZYG-002 | Retire the old fork's built-in ptrace-init implementation in favor of the maintained loader. Users needing ptrace can evaluate a pinned external provider with built-in disabled. No claim that an old ptrace trace is reproduced by the native bridge. |
| ZYG-003 | Restore both shipped Android 14 GrapheneOS specialization descriptors. Device qualification remains separate from descriptor correctness. |
| ZYG-004 | Retire automatic Futile Hide remapping/solist editing. `2202d71b` remaps every matching `/modules/` mapping and ignores protection/remap failures; this is not a stable module API and changes linker-owned memory. Retain supported module unloading and per-process namespace isolation instead. Users dependent on this detection behavior must retain their qualified historical installation or qualify an external provider; no equivalent hiding promise is made. |
| ZYG-005 | Retire the old permanently cached clean namespace optimization. The measured PR26 stale-overlay leak and the external provider's boot-timed cache repair show why capture timing matters. Built-in unmounts the selected process's current namespace; correctness is required before any cache/latency optimization. No claim of a speed improvement. |
| ZYG-006 | Retain the corrected init `onrestart` command and maintained crash rollback. Ordinary patched-boot restart tests exercise this separately from MuMu cold boots. |
| ZYG-007 | Retire mandatory external-only deletion. Keep the optional external route and versioned adapter contract. PR12 still owns Hide/SuList interoperability and migration; it is not enabled by this ADR. |
| ZYG-008 | Preserve a no-injection configuration with built-in off and no external module. This does not silently convert Lite users to a Full always-injecting configuration. Lite's separate always-SuList/module/product migration remains DIST-004/PR12–PR14. |

The existing [feature ledger](../port-ledger.md) retains exact historical sources and all
remaining owners. PR11 completion does not imply PR12 feature completion or PR16 production
promotion. Only evidence-backed entries may be closed.

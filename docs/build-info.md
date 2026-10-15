# Kitsune build identity and migration (PR9)

`kitsune-build.json` is the reviewed product specification. `tools/build_info.py` combines it
with the actual Git source state; Python builds and standalone Gradle builds call that same
generator. Kotlin, C++/Rust, installer scripts and APK assets consume its output. Identity
overrides in `config.prop` or `magisk.versionCode` are rejected.

| Field | Current contract |
|---|---|
| Product version | `0.1.0-dev`; the new maintained Kitsune product sequence |
| Android app code | `31001`, above the inherited `31000`; increase for each distributed update |
| Package | `io.github.huskydg.magisk.next`; retain the installed Next package |
| Upstream | Official `v31.0`, commit `96221b69fae9910b1c0c75c2f92a4ebb2c2dc698` |
| Module compatibility epoch | `31000`, matching that actual upstream implementation |
| Manager/daemon protocol | `1`; independent of both upgrade and module codes |
| Channel | `next-system-experimental`; does not confer production support |
| Source | Full commit, dirty flag and content digest; dirty builds carry `-dirty` |
| Build ID | SHA-256 of the complete generated identity, including source and variant |
| Tags | `kitsune-canary-<full-commit>` for development; `kitsune-v<product-version>` otherwise |
| Signer | Actual verified certificate SHA-256 in the artifact report, together with APK hash/size |

The generator checks the upstream tag/commit and reads its compatibility code from the historical
source. It rejects dirty submodules. Re-editing a file at the same HEAD changes the build ID.
Generated files are rewritten only when their content changes. Packaging rejects native binaries
from a different source state or variant. The final artifact verifier compares the generated JSON,
manifest, shell variables, every ABI's native identity, APK comments, embedded stub and signers.
The signer describes the signed artifact, rather than claiming a certificate before signing.

## Runtime queries

```sh
magisk --version-json          # The invoked binary, no daemon required
magisk --daemon-version-json   # The running daemon; never starts one
magisk --features              # Compiled Kitsune capabilities, one per line
```

The daemon request uses a reserved value outside the historical request range. Existing request
numbers are unchanged. An old daemon rejects the request, rather than treating it as another
fork's privileged command. A manager encountering a legacy daemon can still offer an explicit
installation; equal `31000` values are no longer evidence that manager and runtime match.
Known incompatible protocols cannot be presented as an active supported runtime. Environment
repair requires the running daemon's build/protocol to match the installed utility payload.
Release daemon manager validation uses the Android app code and protocol, independently of the
module epoch, while retaining the existing signer checks. An incompatible code/protocol is refused
without uninstalling the manager or deleting its data; it is distinct from a signer failure.

Capabilities describe compiled support, not enabled settings or device qualification:

- `kitsune.build-info.v1`: the identity and capability query contract.
- `kitsune.system-mode.transaction.v1`: debug builds only; still requires a clean source and
  exact machine qualification before a persistent installation.

No SuList, early-mount or external-provider capability is advertised before its implementation.
Module authors can test an exact capability with `magisk --features | grep -qx <identifier>`.
An unknown option or absent identifier means unavailable. Ordinary upstream module version guards
continue using `MAGISK_VER_CODE=31000` / `magisk -V`; Android code `31001` never reaches those guards.
This epoch asserts the selected upstream API baseline, not that historical Kitsune extensions have
already been ported. The PR7A module profiles retain their exact historical qualification; PR9 does
not claim new universal module/provider compatibility. Future upstream updates must change the
base and its tested compatibility epoch together.

## Upgrade rules

1. A Next manager at code `31000` can update in place to `31001` **with the same signer**.
   Package, app UID, settings and permissions remain Android's existing update domain. A newer
   manager does not silently replace the installed root backend.
2. Historical `io.github.huskydg.magisk`, Lite, official Magisk and randomized hidden packages are
   different identities. A higher code does not create a cross-package or cross-signer upgrade.
   Restore a hidden manager through its existing manager first. Keep an external recovery copy;
   uninstall an old System Mode backend with the manager that owns it, then qualify a clean Next
   installation. Retain supported user module/settings data as described by the existing uninstall
   contract. No automatic legacy payload or database conversion is introduced.
3. If Android reports a signer mismatch, do not bypass verification or reuse the historical public
   key. Production signer transitions, hidden-manager migration breadth and authenticated update
   delivery remain PR10/PR13/PR16 gates. Users relying on unported Kitsune features should retain
   their existing qualified setup until those feature gates close.
4. A local dirty build is diagnostic evidence only. Persistent System Mode continues to reject it;
   no clean-commit claim is synthesized to permit installation.

`scripts/release.sh verify` (or `metadata`) writes `out/release-info.json` after source, ABI,
identity and signer checks. `tag-name` prints the expected fork tag only for a clean source tree.
The script no longer derives official-looking tags from a compatibility integer, changes versions,
commits, pushes or publishes. Production promotion remains PR16, and PR10 owns update-service
authentication. The report is an artifact record, not an authenticated update feed.

## Local verification — 2026-10-14

The PR9 implementation was exercised on MuMuPlayer Pro 1.9.2, VM 0, Android 12 ARM64,
ADB `127.0.0.1:26624`. The installed historical `31.0-kitsune` release daemon was preserved.
The original Next manager APK and private data were saved outside the repository before testing.
Android accepted the same-signer Next manager update from `31000` to `31001` and retained UID
10101. The updated manager launched without a fatal exception; both `BuildInfoTest` instrumentation
cases passed. This proves the existing Next package update, not a historical-package/signer merge.

Both debug and release native runtimes were tested in private mount/PID namespaces with temporary
`/debug_ramdisk`, `/data/adb` and `/cache` filesystems. Local and daemon JSON matched, module epoch
remained `31000`, release omitted the debug-only System Mode capability, and the release runtime
completed 32 concurrent root requests. Exiting namespace PID 1 removed the temporary daemon and
mounts. The installed daemon's PID/version were checked unchanged. No boot installation or
`adb reboot` was used. This is PR9 identity/IPC/SU evidence, not a new persistent System Mode or
physical-phone qualification.

Debug/release builds cover ARM64, ARM32, x86 and x86_64. The artifact verifier checks exact source
identity, manifest/app code, native/module epoch, shell fields, all ABI payloads, 16 KiB alignment,
embedded/standalone stubs and signer-matched test APKs. Native Clippy and Android lint passed;
the legacy manager still compiles. Host regressions include the production Rust APK parser's
compatible, old-code and wrong/missing-protocol cases, plus variant, dirty-content and upstream
identity checks. The normal emulator suite now asserts the running daemon's complete JSON against
the manager's generated identity. CI/physical-device breadth and production signing stay with
their existing roadmap gates.

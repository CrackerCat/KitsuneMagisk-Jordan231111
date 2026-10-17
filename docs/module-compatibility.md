# PR15 module compatibility

Pinned unmodified upstream ZIPs, clean userdata per case, real installation/cold boots/removal, selected functional probes, and official stable failure controls.

Representative widely used modules, not an exhaustive ecosystem ranking. AVD profiles do not simulate OEM hardware. Physical audio, charging and hardware attestation are unqualified.

The production-signed candidate uses io.github.jordan231111.magisk, code 31012,
source 44143a6d2. [The machine record](module-pr15.json) pins each upstream release and SHA-256.
ViPER was retested on candidate31013 after the field-separator fix; its per-run identity is separate.
No module ZIP is redistributed in this repository.

| Module | Version | Observed result | Boundary |
|---|---|---|---|
| [LSPosed/ZygiskNext](https://github.com/LSPosed/ZygiskNext/releases/tag/v1.5.2) | v1.5.2 | Provider activation and client-module combinations passed | Only one provider enabled. Ordinary manager consent passes; stock providers are not the versioned Kitsune SuList adapter and do not imply policy parity. |
| [PerformanC/ReZygisk](https://github.com/PerformanC/ReZygisk/releases/tag/v1.0.0) | v1.0.0 | Provider activation and client-module combinations passed | Only one provider enabled. Ordinary manager consent passes; stock providers are not the versioned Kitsune SuList adapter and do not imply policy parity. |
| [LSPosed/LSPosed](https://github.com/LSPosed/LSPosed/releases/tag/v1.9.2) | v1.9.2 | Manager active on API29; inactive on API35 | The release declares Android 8.1–14 support. Both outcomes match official 30.7 controls. |
| [LSPosed/LSPosed.github.io](https://github.com/LSPosed/LSPosed.github.io/releases/tag/shamiko-414) | shamiko-414 | Incompatible with this fork | 1.2.5 refuses both debug and release Kitsune; official 30.7 and 31.0 controls work. Hiding the manager does not fix it. Zygisk Next does not list it as loaded, and selected-app mount hiding fails. |
| [snake-4/Zygisk-Assistant](https://github.com/snake-4/Zygisk-Assistant/releases/tag/v2.1.4) | v2.1.4 | Selected-app mount hiding passed | Core enforcement was disabled. A real unprivileged app saw the marker before selection and could not see it after the module took ownership. |
| [osm0sis/PlayIntegrityFork](https://github.com/osm0sis/PlayIntegrityFork/releases/tag/v18) | v18 | Install, cold boot and removal passed | Installation and lifecycle only on the account-free AOSP image. No Google integrity verdict or hardware-backed attestation claim. |
| [KOWX712/PlayIntegrityFix](https://github.com/KOWX712/PlayIntegrityFix/releases/tag/v4.9-inject-s) | v4.9-inject-s | Install, cold boot and removal passed | Installation and lifecycle only on the account-free AOSP image. No Google integrity verdict or hardware-backed attestation claim. |
| [5ec1cff/TrickyStore](https://github.com/5ec1cff/TrickyStore/releases/tag/1.4.1) | 1.4.1 | Install, cold boot and removal passed | Keystore modification and hardware attestation verdicts remain unqualified. The process-name probe was inconclusive on both current and stable cores; no external keybox was obtained. |
| [RikkaApps/Riru](https://github.com/RikkaApps/Riru/releases/tag/v26.1.7) | v26.1.7 | Installed, but injection unqualified | Riru reports not loaded on both cores in prepared API35 and API29 comparisons. Lifecycle passes; do not claim working injection. |
| [RikkaApps/Sui](https://github.com/RikkaApps/Sui/releases/tag/v13.5.1) | v13.5.1 | Sui server active; lifecycle passed | Server startup verified alone and with Vector/providers; not every downstream Sui client is qualified. |
| [Magisk-Modules-Repo/busybox-ndk](https://github.com/Magisk-Modules-Repo/busybox-ndk/releases/tag/13614) | 13614 | BusyBox executable and lifecycle verified | Prepared standalone and combined installations report 1.36.1 and remove cleanly. No claim of exhaustive applet equivalence. |
| [programminghoch10/ViPER4AndroidRepackaged](https://github.com/programminghoch10/ViPER4AndroidRepackaged/releases/tag/v87) | v87 | Install, cold boot and removal passed | The 31013 IFS fix keeps the module enabled, publishes both audio-effect configurations and permits removal. The same ZIP passes official30.7. Physical audio/DSP output remains unqualified. |
| [Magisk-Modules-Repo/magiskhidepropsconf](https://github.com/Magisk-Modules-Repo/MagiskHidePropsConf/releases/tag/v6.1.2) | v6.1.2 | Install, cold boot and removal passed | Function-specific hardware behavior is not implied by lifecycle checks. |
| [VR-25/acc](https://github.com/VR-25/acc/releases/tag/v2023.10.16) | v2023.10.16 | Standard module install and removal passed | Initial harness omitted the normal module directory; corrected tests pass both cores. Charging control requires matching physical power-supply hardware. |
| [JingMatrix/Vector](https://github.com/JingMatrix/Vector/releases/tag/v2.2) | v2.2 | Framework and manager active | Corrected action category and Compose UI checks pass on both cores. Real root consent also passes with built-in, ReZygisk and NeoZygisk combinations. |
| [JingMatrix/NeoZygisk](https://github.com/JingMatrix/NeoZygisk/releases/tag/v2.4) | v2.4 | Provider activation and client-module combinations passed | Only one provider enabled. Ordinary manager consent passes; stock providers are not the versioned Kitsune SuList adapter and do not imply policy parity. |

Kitsune’s own Hide and Zygisk Assistant both passed the selected-app mount-visibility probe.
Shamiko did not. With Zygisk Next, the provider did not list Shamiko among loaded modules,
and the same marker remained visible. Installing successfully is not evidence of working hiding.
The [signing-identity controls](device-pr15/shamiko-signing-identity.json) now explain the
rejection: re-signing official Magisk's embedded stub reproduces it with unchanged native code
and version metadata. A manager and stub signed with the same test key retain working manager
root but still fail Shamiko's check. Supporting this fork requires acceptance of its signing
identity by Shamiko; changing Kitsune's authorization or borrowing an official stub is not a fix.

Vector’s manager now uses org.matrix.vector.manager.LAUNCH_MANAGER and Compose UI.
The initial legacy launch/resource-ID observer was corrected; saved UI state and fresh
standalone comparisons verify its Active state. ACC was also rerun after the harness
created the standard Magisk module directory before the first installation.

Provider combinations use one injector at a time. Core enforcement is off when a third-party
hider owns visibility. These results do not certify stock external providers for Kitsune
SuList; that requires the [versioned provider contract](adr/0001-zygisk-provider.md).

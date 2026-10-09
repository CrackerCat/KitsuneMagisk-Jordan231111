# PR8 branch decision — 2026-10-08

Decision: continue development on the official-v31.0-based `next-system` foundation.
Keep `kitsune` as the historical reference until the remaining product gates pass.
PR8 completes the comparison and makes a reversible development decision; it does not
promote a production release, certify physical phones, or complete PR9–PR16.

The selected foundation is `dd5ca5c12e8447344eef5e89f6080e9e2a0d04c8`, based on official
`96221b69fae9910b1c0c75c2f92a4ebb2c2dc698`. The Windows candidate is the retained PR7A CI
APK from `99ab2c55d4441bab2dbd3327e7705ac1d43abe47`; its production code matches the
foundation. The paired current reference is `b416c8ddd900023c8b9dd8d5569395d91bd0dc4c`.
Exact APK digests, preparation and restore results are in the
[Windows lab record](system-mode/pr8-windows-2026-10-08.md).

## Evidence and limits

| Lane | Current reference | Selected foundation | Consequence |
|---|---|---|---|
| Prepared LDPlayer 14.0.9.2, Android 14 x86_64 | Installation failed during runtime metadata normalization; rollback and external restore passed | Install, three vendor-root-off cold boots, policy/module smoke, 48 concurrent SU requests, same-version reinstall, backend uninstall and external restore passed | Continue with Next on this exact prepared image; distinct-version upgrade and UI/post-uninstall boot remain qualification work |
| MuMu Global 6.8.0, Android 12 x86_64 | Same installation failure; rollback and external restore passed on the restored baseline | Install, three vendor-root-off cold boots, module/policy smoke, 48 concurrent SU requests, manager uninstall, uninstalled cold boot and external restore passed | Experimental exact-target result; reinstall refused before writes because the private system image lacked space |
| BlueStacks 5.22.265.1013 Tiramisu64 | Preflight rejected unqualified read-only backing, init metadata and policy state | Same rejection using the common driver | Explicit unsupported System Mode result; preserve the user's existing released root; PR15 owns an adapter if support is advertised |
| Prepared Mac MuMu 1.4.46 ARM64 | Earlier PR5/PR7 records remain tied to their original artifacts | PR7A qualified the v31 foundation, module/provider/SU and uninstall/restore lifecycle | Retain the existing Mac evidence; do not relabel it as Windows testing |
| Ordinary Magisk | PR #26's retained CI/local records cover its stated API/ABI and artifact tuples | PR7A's final 32-job matrix covers ordinary API 23 through current/preview and real 16 KiB lanes | No new app/native product change in PR8; retain exact prior evidence, with physical boot/slot/OTA/recovery breadth owned by PR15 |
| Immutable negative images | Existing API 35/36 characterization records | Existing fail-closed capability contract retained | These images are rejection evidence, never successful persistent System Mode installs |

The Windows matrix is LDPlayer, MuMu Android 12 and BlueStacks. MuMu Android 15 was excluded.
The current/next destructive comparisons used the same restored prepared baselines. No current-line
success was invented after its installer failed. Same-version reinstall is separate from a
distinct-version upgrade. The latter remains unrun in Windows; the MuMu capacity rejection is an
observed negative result. Neither limitation is waived into a supported-image claim.

Ordinary route comparison retains [PR7's evidence](system-mode/mumu-pr7-2026-09-09.md) and
the [PR7A final matrix](https://github.com/Jordan231111/KitsuneMagisk/actions/runs/34476924390).
Select-and-Patch/ramdisk boot, ordinary SU, module lifecycle, hidden-manager and provider checks
are covered only to those records' stated extent. Real `init_boot`/`vendor_boot`, inactive-slot OTA,
recovery ZIP and stock-image restoration remain separate PR15 cases. Emulator root cannot settle
those phone-specific questions.

## Fork disposition

The [reproducible delta inventory](pr8-fork-delta.json) compares tracked app/native/scripts/stub
content against each line's stated upstream base. The historical endpoint changes 172 paths
(82 native); current changes 192 (84 native); Next changes 70 (17 native). The bases differ, so
these are review-size measurements, not a parity score. Exact diff SHA-256 values are retained.

| Component | Disposition on the selected foundation | Remaining owner |
|---|---|---|
| Boot-image parser/patcher, init, policy, resetprop and ordinary SU | Keep the maintained official implementations and the qualified PR7/PR7A integration changes; require a demonstrated gap before importing an older native workaround | PR15 exact boot/layout/SU qualification |
| Persistent System Mode | Keep the versioned transaction, one-shot authorization, init/domain proof, boot rescue, exact ownership/uninstall and external-restore requirements | PR15 target adapters, upgrade breadth and recovery/OTA disposition |
| Host emulator identity | Keep explicit LDPlayer and Windows MuMu Android 12 projections; bind backing layout, controller, hardware identity and transport despite volatile vendor metadata | PR15 additional exact tuples |
| Hide/SuList and daemon namespaces | Port the historical user contract after source/DB/provider review; upstream DenyList is only partial overlap | PR12 core/migration, PR13 UI |
| Built-in/external Zygisk | Retain the tested built-in baseline pending the provider ADR; older built-in removal and Lite's no-Zygisk contract are separately recorded | PR11 |
| Early mounts, `initrc.d`, expanded module partitions and boot stages | Preserve every ledger obligation and the route-specific timing/conflict/recovery fixtures; ordinary module smoke does not establish early visibility | PR14 implementation, PR15 target breadth |
| Identity, channels, stub, signer and manager behavior | Keep foundation containment; replace inherited endpoints through an owned verified service and explicit migration | PR9, PR10, PR13 |
| Unsafe historical mechanisms | Do not reintroduce implicit filename privilege, global signature bypass or public production signing keys merely to match old code; retain evidence and explicit migration/retirement work | PR10/PR15, as assigned in the ledger |

The [port ledger](port-ledger.md) accounts for 192 fork commits, 726 commit/path changes,
69 original-stable source deltas, 102 atomic behaviors and all frozen metadata asset references.
The three additions to the seed capture read-only property serial semantics, the full init-RC path
check and the later Lite artifact-only runtime fallback. First/last fields are bounded source or
published-contract observations. They do not authenticate every old APK's compiled implementation.

[Six mechanisms are retired with evidence](port-history/retirements.json): implicit filename
activation, debug-shell automatic root, public production keys/global signature bypass, global
manager signature-check disablement, blanket release optimization disablement and false upstream
identity. The useful installation, SU, manager and debugging workflows remain. Their replacement
identity/update migrations still have named owners; retirement does not claim those later PRs passed.

Recovered manager/stub signatures and byte digests are recorded separately from publisher/source
bindings. The moved-k4 manager scripts match the surviving source incarnation; native/app bindings
remain limited. Original stable download links return 404, and its recovered embedded stub is not
relabeled as a recovered standalone download. These are accounted archival limits with numbered
dispositions. The ordinary audit rejects missing observations or references; `--release` also rejects
all deferred features and unresolved archive dispositions. PR8 does not retire a historical user
feature merely because its old source or service is unavailable.

## Additional compatibility work

| Improvement | Owner | Measurable acceptance |
|---|---|---|
| Earlier module failure isolation | PR14–PR15 | Inject failure at each publication boundary and timeout; preserve the previous complete plan or disable the failing module, boot successfully and restore exact base bytes |
| Provider conflicts and namespace diagnostics | PR11–PR13 | Detect conflicting enabled providers, identify the selected provider, and compare scoped/control processes without changing unrelated app visibility |
| Image/slot/OTA guidance | PR13–PR15 | Match guidance to measured boot-layout fixtures, reject ambiguous image/slot selection, and preserve the stock recovery path across a tested OTA |

The [early-mount contract](early-mount-pr8.md), concrete inert fixture archives and 75-case route
plan belong to PR8 design. They are not implemented runtime support or captured first-consumer traces.
PR14 must prove publication before the actual consumer on each claimed route, including read-only
and EROFS layouts, encrypted data, conflicts, safe mode and rollback.

## Reversal and promotion

Retain the current source reference, original release observations, exact APKs and external lab
backups. If a later owner cannot preserve a required capability on Next, keep promotion held and
isolate that adapter/feature instead of deleting its ledger row. Users needing an unported historical
feature stay on their existing qualified setup until an explicit upgrade or retirement path is tested.
Do not perform automatic cross-line database or unmanifested legacy conversion.

PR15 must close the advertised exact-target lifecycles and physical-device matrix. PR16 must reject
every deferred/untested historical row and unresolved archive disposition, qualify the exact release
artifact, then make the final production decision. Only after promotion should the old reference be
archived instead of maintained as a second product. This decision does not promote a production
branch or change release tags.

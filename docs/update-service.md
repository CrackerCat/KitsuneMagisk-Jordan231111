# Authenticated manager and stub updates (PR10)

PR10 replaces the inherited manager/stub update routes with one authenticated contract. Production
activation is still pending publication and the live clean-stub acceptance test. It does not close
the remaining root, hiding, module or physical-device release gates.

## Ownership and identity

The service is a small static feed in `Jordan231111/KitsuneMagisk`, on the `update-feed` branch:

```
https://raw.githubusercontent.com/Jordan231111/KitsuneMagisk/update-feed/v1/beta.json
https://raw.githubusercontent.com/Jordan231111/KitsuneMagisk/update-feed/v1/stable.json
https://raw.githubusercontent.com/Jordan231111/KitsuneMagisk/update-feed/v1/canary.json
```

The experimental default is `beta`; stable promotion stays blocked until PR16. Existing installs
remain opted out of background checks. Custom URLs must use HTTPS and end in one of those channel
filenames, and retain the same pinned project signature. There is no unsigned JSON fallback or
public debug update channel. Old Debug selections resolve to the default beta channel,
without changing signer trust or enabling background checks. The full manager retains its DNS-over-HTTPS preference.

One external RSA-3072 keystore signs both production APKs and metadata. The private keystore and
four-field build config are outside the checkout, under `$HOME/.config/kitsune-magisk/signing/`.
They are mode 0600 in a mode-0700 directory. Release APK builds require all four external
signing fields and reject in-checkout configs/keystores and the Android debug-key alias. Passwords are never command-line arguments, repository
files, CI secrets added by this change, logs or APK assets. The public certificate SHA-256 is:

```
9b09eb317c96036185884700d9584e63cc4a2a288825a0172633ba7bfe222ec6
```

`updates/trust.json` contains only public trust data. Every manager/stub also contains its actual
build signer's public certificate. Repackaging a hidden stub preserves that original-manager pin.
Debug and disposable CI builds cannot silently update to another signer. Historical public-key
installations and engineering `.next` installations signed with the debug key require an explicit
backup/reinstall transition before production adoption. No public historical key or signature
bypass is restored. The owner must retain independent protected backups of the production key and
password before distribution; another folder on the same disk is not disaster recovery.

## Wire contract

An envelope has exactly `schema`, `key_id`, `payload`, and `signature`. `payload` is canonical base64
of the UTF-8 JSON bytes. The RSA PKCS#1 SHA-256 signature covers the domain separator
`KitsuneMagisk update v1\n` followed by those exact bytes. Clients reject duplicate/unknown keys,
malformed UTF-8, noncanonical base64, invalid numbers, excess nesting and oversized input.

The signed payload separates its distribution channel (`beta`/`stable`/`canary`) from the APK
build channel (`next-system-experimental`). It records monotonic sequence, issue/expiry times, product and Android
versions, minimum Android API, package, exact source/upstream commits, dirty state, build ID, protocol,
variant, signer, inline release/migration notes, release tag, and separate manager/stub URL/size/SHA-256
descriptors. The publisher derives the minimum API from both APK manifests; clients reject unsupported
Android versions before downloading, and API 24+ also compares the parsed manifest requirement.
Metadata is limited to 128 KiB, manager APKs to 200 MiB and stubs to 8 MiB. Validity is at most
30 days (14 by default). Public publication tooling rejects dirty sources and debug artifacts.
QA fixtures are signed test inputs in ignored `out/`, explicitly separate from feed preparation.

Rollback protection persists accepted sequence and payload hash per channel, the highest accepted
Android code and its APK hash across channels, and the latest valid observed time. Switching channels
does not reset the floor. The same sequence cannot change content; the same app code cannot identify
different APK bytes. A clock rollback beyond five minutes, expired metadata or corrupt saved state
fails closed. Refreshing a channel requires a higher sequence; the publisher can authenticate expired
old metadata to preserve its floor. Clearing app data/root-controlled rollback is outside the remote
replay boundary; the installed/embedded app-code floor and expiry still apply.

All network operations are bounded and run off the manager UI thread. Metadata reads have a
60-second transfer budget and APK reads a ten-minute budget, in addition to bounded connection/read
timeouts; slow trickles cannot hold a downloader indefinitely. Metadata redirects stay on
the selected HTTPS host. APK descriptors must name this repository's release/tag, and redirects are
limited to GitHub and its release-asset host. Credentials, plaintext redirects, unexpected encoding
and excessive redirect chains are rejected. Streams are length/hash checked before any installation.
Stopped jobs/services cancel their downloads, interrupted APK writes abandon the installer session,
and unsuccessful metadata checks still finish their scheduler job.

The platform verifies the APK signature and exact signer/package/version; the APK's build info and
embedded stub must also match the signed record. Files are written to private temporary paths,
synced, verified, made read-only and atomically renamed. Failed downloads retain the current manager.
Unfinished `.part` files are never loadable. Hidden-manager current/update/development/seed APKs are
verified before creating a classloader, independently of whether they arrived through this client.
This uses the platform's certificate collection with verification enabled, as in
[AOSP PackageManager](https://android.googlesource.com/platform/frameworks/base/+/4be0bf277e19be48f68bb50904ecbd9e872c751e/core/java/android/content/pm/PackageManager.java).

## Candidate preparation and publication

1. Review and commit the source, increase `kitsune-build.json`'s Android upgrade code for new bytes,
   and build/test the exact candidate with the external production config. PR10 uses code `31002`
   and stub revision `41`. Preserve the PR9 module epoch `31000` and manager/daemon protocol `1`.
2. Run `scripts/release.sh verify`. The artifact check also binds the manager/stub trust assets to
   the reviewed trust root and their actual signers. Retain the tests and artifact report.
3. Prepare the signed metadata without publishing or rebuilding:

   ```sh
   scripts/env.py python3 tools/update_service.py prepare \
     --config "$HOME/.config/kitsune-magisk/signing/production.prop" \
     --channel beta --sequence 1 --notes /path/to/reviewed-release-notes.md \
     --output out/update-feed/v1/beta.json
   ```

4. Enable [GitHub release immutability](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
   before publication. Create a draft prerelease for the exact fork tag/source, attach only the
   tested production manager and matching stub plus public evidence, then publish. Do not publish
   debug/instrumentation APKs, signing configs, private keys or `out/update-fixtures`. Never replace tested bytes.
5. Commit the signed channel file to the separate `update-feed` branch after its assets exist.
   Preserve the previous channel files and compare the remote sequence before changing a feed.
   A metadata refresh uses the same APK bytes and a higher sequence; new APK bytes require a higher
   Android code. Repository/branch publication is an explicit maintainer operation.
6. Download and verify the actual public files, then install a clean production stub on the test
   emulator and verify that it obtains exactly the advertised manager:

   ```sh
   scripts/env.py python3 tools/update_service.py verify-published \
     --url https://raw.githubusercontent.com/Jordan231111/KitsuneMagisk/update-feed/v1/beta.json \
     --channel beta --output out/published-update-verification
   ```

No production key is needed by ordinary CI. CI signs its APKs/fixtures with its disposable key and
runs the same verifier. `tools/update_service.py test-fixtures --config /path/to/config.prop`
prepares the bounded failure corpus; `UpdateServiceTest` is included in the normal Android matrix.
Local MuMu tests must use full application close/open for any cold boot, never `adb reboot`.

## Historical distribution and remaining gates

Original Full/Lite and moved-tag release provenance remains in the PR8 ledger. Their dead/unsigned
endpoints are not trusted redirects into the new feed. A matching old version label is not an
authenticated upgrade path. Users needing unported Lite/SuList/module capabilities keep their
existing qualified setup until the relevant feature PR closes; this updater does not retire them.
The [historical module template](port-history/module-template.json) retains its exact 8,537-byte
digest and immutable archive locator. It is an archival reference for the old module API, not an
advertised installer/template for the new runtime. PR14 owns that API's tested migration.

Live feed publication and successful clean-stub download evidence remain PR10 activation gates.
Independent protected key backup remains a production-promotion requirement under P0.7/PR16. This document must not be read as proof of production-phone root qualification.


## Local evidence

The four-ABI production-signed and debug artifacts passed the identity/signature/alignment gate.
The shared verifier and download lifecycle passed 20 instrumentation tests (multiple fault cases per test), including
real platform APK signature rejection, on MuMuPlayer Pro 1.9.2 / Android 12 ARM64. After the user
selected the second instance, VM 0's original manager/root were restored and its test files removed.
Remaining work uses VM 1 only (`127.0.0.1:26656`); it started without a Magisk package. The clean
production stub showed a verification error for the unpublished feed and remained at version code 1.
A manual same-signer install then retained its UID while updating to code 31002, and all 22 update
and build-identity tests passed on that clean instance. This is not yet the successful live-feed
acceptance result. No `adb reboot` or persistent root installation was used.

The host suite exposed a macOS process-signal permission error in the inherited qualification
harness. It is now an explicit indeterminate lifecycle result, so recovery cannot proceed without
proof that the process group stopped; a focused injected-denial regression covers it.
The complete host suite passed 274 tests with one Linux-only skip. App/stub lint and the legacy
app's Kotlin compilation passed. These local checks precede public activation and its separate
download/clean-stub acceptance record.

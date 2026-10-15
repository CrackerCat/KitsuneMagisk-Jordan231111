# ReZygisk Kitsune Hide v1 source adapter

The patch applies only to Jordan231111/ReZygisk
`c9b7dc0761b8bbff1b3216a45cb6234a19b6310c` (`v1.0.0-554`, GPL-3.0).
It is optional source, not a bundled injector. The stock release and NeoZygisk
releases do not implement this contract. Do not add the capability declaration
file to an unmodified provider.

The adapter queries `magisk --hide check UID PROCESS` for every specialization
and queries the verified manager UID through the same interface. It uses the
running mode, never the next-boot `sulist` database setting. Failed/malformed
policy queries request cleanup and do not grant root or manager identity.
Selected processes skip module callbacks; preloaded provider/loader mappings
are not claimed invisible. The provider remains the sole namespace owner.

Build from the pinned clean checkout with its recursive submodules, apply
`rezygisk-hide-v1.patch`, then run `make release` through `scripts/env.py` with
`TOOLCHAIN` pointing to the host's Android NDK LLVM toolchain. The patch adds
`module/src/kitsune-hide-v1` to the ZIP. Do not install the stock upstream update
over this adapter: it would remove its contract. Verify the exact artifact
against the PR12 runtime evidence before treating a tuple as qualified.

To select it, disable built-in Zygisk and every other external provider,
install the adapted module, run `magisk --hide provider external`, and cold
boot. Check that `--hide status` reports `engine=external`. Enable Hide with
`magisk --hide enable`. `mode sulist` takes effect on another cold boot.
Returning to core requires disabling/removing the provider, selecting
`provider core`, and cold booting. Safe mode and the ordinary recovery paths
remain available. A provider declaration is not injection-health attestation.

#!/usr/bin/env bash
#
# fetch-cran-tarballs.sh — download every CRAN-submission R source tarball from
# the nirs4all ecosystem GitHub Releases and drop a ready-to-paste "optional
# comments" Markdown next to them.
#
# The cockpit is read-only over public release state; this is a convenience
# fetcher for the maintainer's MANUAL CRAN web-form submission
# (https://cran.r-project.org/submit.html). It reimplements nothing — it pulls
# the assets each repo's release-r workflow already built and validated.
#
# Usage:
#   scripts/fetch-cran-tarballs.sh [OUTDIR]        # default OUTDIR=dist/cran
#   N4A_OWNER=GBeurier scripts/fetch-cran-tarballs.sh /tmp/cran
#
# Requires: gh (authenticated: `gh auth login`) and sha256sum/shasum.
set -euo pipefail

OWNER="${N4A_OWNER:-GBeurier}"
OUTDIR="${1:-${N4A_CRAN_OUT:-dist/cran}}"

# The repos whose Releases carry a CRAN-submission R source tarball. Formats is
# intentionally absent: current release policy keeps nirs4allformats on
# R-universe only.
REPOS=(nirs4all-methods nirs4all-io nirs4all-datasets nirs4all-core)

# A CRAN R source tarball is `<Rpkg>_<version>.tar.gz` for these exact package
# names. The anchored `_[0-9]` after the name (and "no hyphen before the version")
# excludes, on the same Releases: the Python sdists (e.g. nirs4all_formats-…),
# the `-src` bundles, and the `-capi-` C-ABI archives.
R_TARBALL_RE='^(n4m|pls4all|nirs4allio|nirs4alldatasets|nirs4all)_[0-9][^-]*\.tar\.gz$'

command -v gh >/dev/null 2>&1 || { echo "error: gh CLI is required — https://cli.github.com" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: gh is not authenticated — run 'gh auth login'" >&2; exit 1; }
if command -v sha256sum >/dev/null 2>&1; then
  sha256_file() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
  sha256_file() { shasum -a 256 "$1" | awk '{print $1}'; }
else
  echo "error: sha256sum or shasum is required" >&2
  exit 1
fi

mkdir -p "$OUTDIR"
SUMS_TMP="$OUTDIR/.SHA256SUMS.tmp"
: > "$SUMS_TMP"
trap 'rm -f "$SUMS_TMP"' EXIT
echo "→ owner=$OWNER  output=$OUTDIR"
echo

found=0
for repo in "${REPOS[@]}"; do
  tag=$(gh release view -R "$OWNER/$repo" --json tagName --jq .tagName 2>/dev/null || true)
  if [ -z "$tag" ]; then
    echo "  ! $repo: no published release — skipped"
    continue
  fi
  mapfile -t assets < <(gh release view "$tag" -R "$OWNER/$repo" --json assets --jq '.assets[].name' 2>/dev/null \
                          | grep -E "$R_TARBALL_RE" || true)
  if [ "${#assets[@]}" -eq 0 ]; then
    echo "  - $repo $tag: no R tarball on the release"
    continue
  fi
  for a in "${assets[@]}"; do
    rm -f "$OUTDIR/$a"            # gh release download has no --clobber; overwrite by hand
    gh release download "$tag" -R "$OWNER/$repo" --pattern "$a" --dir "$OUTDIR"
    actual_sha="$(sha256_file "$OUTDIR/$a")"
    release_digest="$(gh release view "$tag" -R "$OWNER/$repo" --json assets --jq ".assets[] | select(.name == \"$a\") | .digest" 2>/dev/null || true)"
    expected_sha="${release_digest#sha256:}"
    [ "$expected_sha" = "null" ] && expected_sha=""
    if [ -n "$expected_sha" ] && [ "$expected_sha" != "$actual_sha" ]; then
      echo "error: checksum mismatch for $repo $tag asset $a" >&2
      echo "       expected: $expected_sha" >&2
      echo "       actual:   $actual_sha" >&2
      exit 1
    fi
    printf '%s  %s\n' "$actual_sha" "$a" >> "$SUMS_TMP"
    if [ -n "$expected_sha" ]; then
      echo "  ✓ $repo $tag → $a  sha256 verified"
    else
      echo "  ✓ $repo $tag → $a  sha256 recorded"
    fi
    found=$((found + 1))
  done
done

if [ "$found" -eq 0 ]; then
  echo "error: downloaded 0 tarballs — check 'gh auth status' and the release tags" >&2
  exit 1
fi
mv "$SUMS_TMP" "$OUTDIR/SHA256SUMS"
trap - EXIT

# ----------------------------------------------------------------------------
# Optional-comments Markdown (one block per package, paste into the CRAN form).
# ----------------------------------------------------------------------------
MD_PATH="$OUTDIR/CRAN-optional-comments.md"
{
  echo "<!-- generated $(date -u +%FT%TZ) by scripts/fetch-cran-tarballs.sh — do not edit by hand -->"
  cat <<'MD'
# CRAN submission — optional comments (nirs4all ecosystem)

Submit each tarball in this folder at <https://cran.r-project.org/submit.html>
and paste the matching block below into the form's *Optional comments* box.
`SHA256SUMS` records the downloaded source-tarball hashes; when GitHub exposes a
Release asset digest, this script verifies the local file against it before the
bundle is considered ready.
Each package also keeps a longer repo-side `cran-comments.md` next to its R
package root; those files are intentionally excluded from the R source tarball
and are meant for maintainer/submission notes, not package payload.

**Submit-now vs R-universe-first**

* CRAN-ready now (≤10 MB, clean): `n4m`, `pls4all`, `nirs4allio`.
* Size exception needed: `nirs4alldatasets` (~24 MB) exceeds CRAN's 10 MB soft
  cap. The matching comments flag the reason.
* R-universe-only: `nirs4allformats`; do not submit it to CRAN in the current
  release train.
* R-universe-first: `nirs4all` (R binding of `nirs4all-core`) — its Suggests (the ecosystem R packages)
  are not yet on CRAN, so R-universe is the natural channel until they land.

---

## n4m_<ver>.tar.gz
```
New submission. n4m is a portable Partial Least Squares (PLS) / NIRS engine: a
C++17/C numerical core (222 translation units) vendored under src/vendor/ and
compiled from source at install. Pure C/C++ — no Fortran, no external system
library, no non-default compilation flags (the spline smoother is a from-scratch
C Reinsch implementation). GNU make is declared in SystemRequirements (Makevars
enumerate the 222 sources via $(shell find ...)). License: CeCILL-2.1. Imports
only stats. R CMD check --as-cran: 0 ERROR, 0 WARNING, 2 NOTES — (1) New
submission; (2) a -march=nocona flag injected by conda-forge R's own Makeconf on
our local check host, not by the package (absent on CRAN's vanilla R). Submission-
grade checks also run on the GitHub Actions matrix (Ubuntu R release+devel, macOS
arm64, Windows). Maintainer: Grégory Beurier (CIRAD), gregory.beurier@cirad.fr.
```

## pls4all_<ver>.tar.gz
```
New submission. pls4all is the slim, PLS-focused distribution carved from the
nirs4all-methods library — the same C++17/C numerical core (222 translation
units) vendored under src/vendor/ and compiled at install. Pure C/C++ — no
Fortran, no external system library, no non-default compilation flags. GNU make in
SystemRequirements. License: CeCILL-2.1. Imports only stats. R CMD check --as-cran:
0 ERROR, 0 WARNING, 2 NOTES — New submission, and a -march=nocona flag from
conda-forge R's own Makeconf on our local host (not from the package; absent on
CRAN). Maintainer: Grégory Beurier (CIRAD), gregory.beurier@cirad.fr.
```

## nirs4allio_<ver>.tar.gz
```
This is a new submission.

nirs4allio is a thin R binding for the Rust-first nirs4all-io dataset-assembly
bridge for the nirs4all NIRS / spectroscopy ecosystem. It exposes the stable
n4io_* C ABI to R: normalize arbitrary inputs into a canonical DatasetSpec, infer
a DatasetPlan, and validate a DatasetSpec. The low-level surface is JSON in / JSON
out; an idiomatic nio_* layer accepts native R inputs and returns typed S3 objects.
License: CeCILL-2.1 | AGPL-3.

Self-contained source tarball: the package vendors the nirs4all-io Rust core and
its crates.io transitive dependencies (shipped compressed as vendor.tar.xz) and
compiles them OFFLINE into a static library at install time via src/Makevars(.win)
(no network, no external repository crates/). The install never writes to ~/.cargo
or ~/.rustup (build-local CARGO_HOME + CARGO_TARGET_DIR, pruned after linking);
cargo runs with -j 2. The C ABI header is committed (src/nirs4all_io.h). The
Cargo / rustc toolchain is declared in SystemRequirements.

R CMD check --as-cran: 0 ERRORs, 0 WARNINGs. The NOTEs are the first-submission
note (with a title-case sub-note on the product name "nirs4all", intentionally
lower-case) and local conda-toolchain artefacts (-march=nocona from conda's
Makeconf; an nm symbol-table parser quirk on the static Rust archive) that do not
occur on CRAN's toolchain. No network access during install/examples/tests;
imports only jsonlite. Maintainer: Grégory Beurier (CIRAD), gregory.beurier@cirad.fr.
```

## nirs4alldatasets_<ver>.tar.gz
```
Update of the existing CRAN package nirs4alldatasets (0.2.0 -> 0.3.5).
nirs4alldatasets is a thin R binding (a small C shim over the stable n4ds_* C
ABI) for the Rust-first nirs4all-datasets acquisition core: resolve a dataset id
from the catalog into a version-pinned download contract, fetch the canonical
Parquet (Dataverse/Zenodo/figshare) with SHA-256 verification into a local cache,
and re-verify a cached directory offline. It compiles the vendored Rust core into
a static library OFFLINE at install. License: MIT.

CRAN Policy compliance: the install never writes to ~/.cargo or ~/.rustup —
CARGO_HOME and CARGO_TARGET_DIR are build-local and wiped after linking; cargo runs
with -j 2; rustc/cargo versions are echoed before compiling; vendored crates ship
compressed (vendor.tar.xz) with dev/build (cbindgen) deps stripped and ~76 MB of
unused Windows import-library blobs pruned. Toolchain in SystemRequirements.

R CMD check --as-cran: 0 ERRORs, 0 WARNINGs; NOTES are the expected CRAN incoming
title-case/package-size notes plus local conda-toolchain artefacts
(-march=nocona, an nm parser quirk) absent on CRAN. Source tarball:
24,666,282 bytes. It needs a size exception: the package ships no dataset
payloads, but it must vendor the Rust acquisition core and its crates.io
dependencies plus embedded catalog metadata so CRAN installation/checks are fully
offline and reproducible. Imports only jsonlite. Maintainer: Grégory Beurier
(CIRAD), gregory.beurier@cirad.fr.
```

## nirs4all_<ver>.tar.gz  (core aggregate)
```
New submission. nirs4all (the R binding of nirs4all-core) is a PURE-R aggregate
(NeedsCompilation: no): no compiled code, nothing to build beyond byte-compiling
the R sources, so none of the Rust / ~.cargo / Makevars considerations of the
compiled siblings apply. It is an umbrella that exposes the ecosystem (NIRS file
readers, dataset assembly, datasets catalog, PLS engine, dag-ml coordinators)
behind one R surface and delegates all parsing/numerical/pipeline work upstream.
Imports: jsonlite, yaml only. License: CeCILL-2.1 | AGPL (>= 3).

The aggregated upstream R packages (nirs4allformats, nirs4allio, nirs4alldatasets,
n4m, dagmldata) are in Suggests, used conditionally behind requireNamespace(), and
served from R-universe via Additional_repositories — they are not yet on mainstream
CRAN. R CMD check --as-cran: 0 ERROR, 0 WARNING. Expected NOTES: New submission;
"Suggests or Enhances not in mainstream repositories" for the R-universe packages;
and title-case on the lower-case product name "nirs4all". Because the Suggests
are not yet on CRAN, R-universe is the natural channel for this package until the
upstreams land on CRAN. Maintainer: Grégory Beurier (CIRAD),
gregory.beurier@cirad.fr.
```
MD
} > "$MD_PATH"

echo
echo "Downloaded ${found} tarball(s):"
( cd "$OUTDIR" && for f in *.tar.gz; do [ -e "$f" ] || continue; printf '  %-40s %8s\n' "$f" "$(du -h "$f" | cut -f1)"; done )
echo
echo "Checksums → $OUTDIR/SHA256SUMS"
echo "Optional comments → $MD_PATH"
echo "Submit each tarball at https://cran.r-project.org/submit.html"

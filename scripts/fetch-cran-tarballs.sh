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
# Requires: gh (authenticated: `gh auth login`).
set -euo pipefail

OWNER="${N4A_OWNER:-GBeurier}"
OUTDIR="${1:-${N4A_CRAN_OUT:-dist/cran}}"

# The repos whose Releases carry a CRAN R source tarball.
REPOS=(nirs4all-methods nirs4all-formats nirs4all-io nirs4all-datasets nirs4all-core)

# A CRAN R source tarball is `<Rpkg>_<version>.tar.gz` for these exact package
# names. The anchored `_[0-9]` after the name (and "no hyphen before the version")
# excludes, on the same Releases: the Python sdists (e.g. nirs4all_formats-…),
# the `-src` bundles, and the `-capi-` C-ABI archives.
R_TARBALL_RE='^(n4m|pls4all|nirs4allformats|nirs4allformats\.lite|nirs4allio|nirs4alldatasets|nirs4all)_[0-9][^-]*\.tar\.gz$'

command -v gh >/dev/null 2>&1 || { echo "error: gh CLI is required — https://cli.github.com" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: gh is not authenticated — run 'gh auth login'" >&2; exit 1; }

mkdir -p "$OUTDIR"
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
    echo "  ✓ $repo $tag → $a"
    found=$((found + 1))
  done
done

if [ "$found" -eq 0 ]; then
  echo "error: downloaded 0 tarballs — check 'gh auth status' and the release tags" >&2
  exit 1
fi

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
The full, shipped-in-tarball `cran-comments.md` lives in each package under
`bindings/r/<pkg>/cran-comments.md`.

**Submit-now vs R-universe-first**

* CRAN-ready now (≤10 MB, clean): `n4m`, `pls4all`, `nirs4allio`.
* Size exception needed: `nirs4allformats` (~13 MB), `nirs4allformats.lite`
  (~10 MB), and `nirs4alldatasets` (~24 MB) exceed or sit at CRAN's 10 MB soft
  cap. The matching comments flag the reason; otherwise keep them on R-universe.
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

## nirs4allformats_<ver>.tar.gz
```
New submission. nirs4allformats is a thin R binding for the Rust-first
nirs4all-formats engine (~58 NIRS/spectroscopy format families); it compiles a
vendored extendr static library OFFLINE at install. License: MIT + file LICENSE.

CRAN Policy compliance: the install NEVER writes to ~/.cargo or ~/.rustup.
src/Makevars(.win) set CARGO_HOME and CARGO_TARGET_DIR build-local (inside the
package tree); a post-link rust_clean rule then wipes target/, the build-local
CARGO_HOME and the extracted vendor/, so R CMD check scans no third-party build
artefacts (the GNU-make-extension Makefiles and a stray CITATION.cff inside the
vendored C-library crates are deleted by ./configure, with their .cargo-checksum
entries removed). cargo runs with -j 2; rustc/cargo --version are echoed before
compiling. Verified by an offline install under a pristine fake HOME (no .cargo is
created). The Cargo/rustc toolchain is declared in SystemRequirements.

R CMD check --as-cran: 0 ERROR. The only WARNING is the Rust-std `abort` reference
(panic / allocation-failure path) — inherent to linking any Rust static library
and the known WARNING CRAN tolerates for Rust packages. NOTES: New submission plus
local conda-toolchain artefacts (-march=nocona, an nm parser quirk) absent on CRAN.

Note on size: this ~13 MB tarball is the COMPLETE reader set (incl. Parquet/Arrow,
HDF5/netCDF, MATLAB) and exceeds the 10 MB soft cap — it may need a size exception.
The smaller sibling nirs4allformats.lite (~10.5 MB, Parquet dropped) is submitted
alongside. Imports only jsonlite. Maintainer: Grégory Beurier (CIRAD).
```

## nirs4allformats.lite_<ver>.tar.gz
```
New submission. nirs4allformats.lite is the smaller variant of nirs4allformats:
the complete reader set MINUS the Parquet/Arrow reader (the single biggest
dependency); it keeps HDF5/netCDF, MATLAB and every core reader. Same Rust core,
same exported R API. Feeding it a Parquet file returns a clean error naming the
complete package and the exact install line. License: MIT + file LICENSE.

CRAN Policy compliance is identical to nirs4allformats: no ~/.cargo / ~/.rustup
writes (build-local CARGO_HOME + CARGO_TARGET_DIR, post-link rust_clean), cargo
-j 2, rustc/cargo versions echoed before compiling, offline vendored build,
toolchain in SystemRequirements.

R CMD check --as-cran: 0 ERROR; the only WARNING is the inherent Rust-std `abort`
reference. NOTES: New submission + local conda-toolchain artefacts absent on CRAN.
Source tarball ~10.5 MB (just over the 10 MB soft cap — may need a size exception).
Imports only jsonlite. Maintainer: Grégory Beurier (CIRAD).
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
New submission. nirs4alldatasets is a thin R binding (a small C shim over the
stable n4ds_* C ABI) for the Rust-first nirs4all-datasets acquisition core:
resolve a dataset id from the catalog into a version-pinned download contract,
fetch the canonical Parquet (Dataverse/Zenodo/figshare) with SHA-256 verification
into a local cache, and re-verify a cached directory offline. It compiles the
vendored Rust core into a static library OFFLINE at install. License: MIT.

CRAN Policy compliance: the install never writes to ~/.cargo or ~/.rustup —
CARGO_HOME and CARGO_TARGET_DIR are build-local and wiped after linking; cargo runs
with -j 2; rustc/cargo versions are echoed before compiling; vendored crates ship
compressed (vendor.tar.xz) with dev/build (cbindgen) deps stripped and ~76 MB of
unused Windows import-library blobs pruned. Toolchain in SystemRequirements.

R CMD check --as-cran: 0 ERRORs, 0 WARNINGs; NOTES are New submission plus local
conda-toolchain artefacts (-march=nocona, an nm parser quirk) absent on CRAN.
Source tarball ~24 MB and needs a size exception: the package ships no dataset
payloads, but it must vendor the Rust/core/io/formats crates and their crates.io
dependencies so CRAN installation is fully offline and reproducible. Imports
only jsonlite. Maintainer: Grégory Beurier (CIRAD), gregory.beurier@cirad.fr.
```

## nirs4all_<ver>.tar.gz  (core aggregate)
```
New submission. nirs4all (the R binding of nirs4all-core) is a PURE-R aggregate
(NeedsCompilation: no): no compiled code, nothing to build beyond byte-compiling
the R sources, so none of the Rust / ~.cargo / Makevars considerations of the
compiled siblings apply. It is an umbrella that exposes the ecosystem (NIRS file
readers, dataset assembly, datasets catalog, PLS engine, dag-ml coordinators)
behind one R surface and delegates all parsing/numerical/pipeline work upstream.
Imports: jsonlite, yaml only. License: MIT + file LICENSE.

The aggregated upstream R packages (nirs4allformats, nirs4allio, nirs4alldatasets,
n4m, dagmldata) are in Suggests, used conditionally behind requireNamespace(), and
served from R-universe via Additional_repositories — they are not yet on mainstream
CRAN. R CMD check --as-cran: 0 ERROR, 0 WARNING, 3 NOTES — New submission;
"packages suggested but not available" for those R-universe packages (expected,
optional); a future-file-timestamp note. Because the Suggests are not yet on CRAN,
R-universe is the natural channel for this package until the upstreams land on CRAN.
Maintainer: Grégory Beurier (CIRAD), gregory.beurier@cirad.fr.
```
MD
} > "$MD_PATH"

echo
echo "Downloaded ${found} tarball(s):"
( cd "$OUTDIR" && for f in *.tar.gz; do [ -e "$f" ] || continue; printf '  %-40s %8s\n' "$f" "$(du -h "$f" | cut -f1)"; done )
echo
echo "Optional comments → $MD_PATH"
echo "Submit each tarball at https://cran.r-project.org/submit.html"

#!/usr/bin/env bash
#
# fetch-cran-tarballs.sh — download every CRAN-submission R source tarball from
# the nirs4all ecosystem GitHub Releases and drop a maintainer-review "optional
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
REPOS=(nirs4all-methods nirs4all-io nirs4all-datasets nirs4all-r)

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
# CRAN submission — maintainer review notes (nirs4all ecosystem)

These downloads are not a CRAN-ready verdict and this script submits nothing.
Before using the manual form at <https://cran.r-project.org/submit.html>, review
and complete the matching notes from the selected release's DESCRIPTION,
LICENSE/COPYRIGHTS, package-owned cran-comments.md and actual current check logs.
Do not carry forward an older version's size, license, system requirements or
check results. R-universe build/check success is separate from CRAN acceptance;
WebR build-only jobs do not establish R CMD check or runtime qualification.

`SHA256SUMS` records the downloaded source-tarball hashes; when GitHub exposes a
Release asset digest, this script verifies the local file against it.
The selected version is in each filename; the terminal output reports its actual
local archive size. Assess any archive size-exception requirements from that file.

* R-universe-only: `nirs4allformats`; do not submit it to CRAN in the current
  release policy. It is intentionally absent from this fetcher's repository list.
* `nirs4all` is the separate R SDK owned by `nirs4all-r`; do not substitute the
  retired aggregate archive from `nirs4all-core`.
* Submission remains a maintainer action for every other downloaded package.

## n4m_<ver>.tar.gz

Record the actual version, license, compilation/system requirements, check-log
URLs, complete ERROR/WARNING/NOTE results and maintainer response to each NOTE
from the selected Methods R source release. Do not reuse an older compiler or
translation-unit inventory as a current claim.

## pls4all_<ver>.tar.gz

Record the corresponding PLS source-release evidence independently of n4m,
including the exact license and all check notes.

## nirs4allio_<ver>.tar.gz

Review the current offline Rust vendor bundle, system requirements, archive size
and all actual check notes, including any inst/LICENSE metadata NOTE. Copy the
license declaration from the selected archive, not from an earlier template.

## nirs4alldatasets_<ver>.tar.gz

Review the current catalog/source provenance, redistribution notices, offline
vendor bundle, exact archive size and any size-exception requirements. Preserve
explicit source-alignment assumptions; do not turn an accepted export into an
independent certification of unavailable originals.

## nirs4all_<ver>.tar.gz  (separate R SDK)

Use the selected nirs4all-r release's DESCRIPTION and package-owned checks.
Document the supported upstream packages, optional controller requirements and
any packages outside CRAN. Record compatibility minimums for trained-envelope
exchange separately from native Methods payload decoding.

MD
} > "$MD_PATH"

echo
echo "Downloaded ${found} tarball(s):"
( cd "$OUTDIR" && for f in *.tar.gz; do [ -e "$f" ] || continue; printf '  %-40s %8s\n' "$f" "$(du -h "$f" | cut -f1)"; done )
echo
echo "Checksums → $OUTDIR/SHA256SUMS"
echo "Optional comments → $MD_PATH"
echo "Review the selected source releases and current check logs before any manual CRAN submission."

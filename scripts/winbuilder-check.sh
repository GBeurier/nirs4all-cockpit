#!/usr/bin/env bash
#
# winbuilder-check.sh — pull the CRAN R source tarballs and upload them to
# win-builder for a real R CMD check on the SAME environment as CRAN's incoming
# pretest (R-devel Windows + Linux), WITHOUT submitting to CRAN. win-builder
# emails the per-package result to the package Maintainer (gregory.beurier@cirad.fr).
#
# Use this to validate a fix (e.g. a Windows install ERROR) before the formal
# CRAN web-form resubmission, so you never burn a CRAN round-trip on a guess.
#
# It first runs scripts/fetch-cran-tarballs.sh to pull the latest tarballs, then
# uploads the selected ones over anonymous FTP (curl) and confirms each with the
# server's "226 Transfer complete".
#
# Usage:
#   scripts/winbuilder-check.sh                              # pull all + submit all to R-devel
#   scripts/winbuilder-check.sh nirs4allio nirs4alldatasets  # only these packages
#   scripts/winbuilder-check.sh --queue R-release            # different win-builder queue
#   scripts/winbuilder-check.sh --no-pull nirs4allformats    # submit what's already in dist/cran
#   scripts/winbuilder-check.sh --dry-run                    # show what WOULD be submitted
#
# Requires: curl (always), and gh (only when pulling — i.e. not with --no-pull).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUEUE=R-devel
DIR="${N4A_CRAN_OUT:-dist/cran}"
PULL=1; DRYRUN=0; YES=0
PKGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --queue)   QUEUE="$2"; shift 2;;
    --dir)     DIR="$2"; shift 2;;
    --no-pull) PULL=0; shift;;
    --dry-run) DRYRUN=1; shift;;
    -y|--yes)  YES=1; shift;;
    -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *)  PKGS+=("$1"); shift;;
  esac
done

command -v curl >/dev/null 2>&1 || { echo "error: curl is required" >&2; exit 1; }
case "$QUEUE" in
  R-devel|R-release|R-oldrelease) ;;
  *) echo "error: --queue must be one of R-devel | R-release | R-oldrelease" >&2; exit 2;;
esac

# 1. pull (reuse the sibling fetcher; it is the single source of the download logic)
if [ "$PULL" = 1 ]; then
  echo "→ pulling CRAN R tarballs into $DIR"
  "$HERE/fetch-cran-tarballs.sh" "$DIR" >/dev/null
fi

# 2. select the tarballs to submit (all R tarballs in DIR, optionally filtered by package name)
shopt -s nullglob
all=("$DIR"/*.tar.gz)
[ "${#all[@]}" -gt 0 ] || { echo "error: no tarballs in $DIR — run without --no-pull, or pass --dir" >&2; exit 1; }
sel=()
for f in "${all[@]}"; do
  b="$(basename "$f")"
  if [ "${#PKGS[@]}" -eq 0 ]; then
    sel+=("$f")
  else
    for p in "${PKGS[@]}"; do [ "${b%%_*}" = "$p" ] && { sel+=("$f"); break; }; done
  fi
done
[ "${#sel[@]}" -gt 0 ] || { echo "error: no tarballs matched: ${PKGS[*]}" >&2; exit 1; }

echo "→ win-builder queue: $QUEUE   |   ${#sel[@]} tarball(s) to submit:"
for f in "${sel[@]}"; do printf '    %-40s %s\n' "$(basename "$f")" "$(du -h "$f" | cut -f1)"; done
echo "  NOTE: win-builder emails one result per tarball to the package Maintainer."

if [ "$DRYRUN" = 1 ]; then echo "DRY RUN — nothing uploaded."; exit 0; fi

if [ "$YES" != 1 ]; then
  read -r -p "Submit ${#sel[@]} tarball(s) to win-builder $QUEUE? [y/N] " ans
  case "$ans" in [yY]|[yY][eE][sS]) ;; *) echo "aborted."; exit 0;; esac
fi

# 3. upload over anonymous FTP, confirming each with the server's 226 response
ok=0
for f in "${sel[@]}"; do
  b="$(basename "$f")"
  if out="$(curl -v --connect-timeout 25 --max-time 300 -T "$f" "ftp://win-builder.r-project.org/$QUEUE/" 2>&1)" \
       && grep -q '226' <<<"$out"; then
    echo "  ✓ $b — 226 Transfer complete"
    ok=$((ok + 1))
  else
    echo "  ✗ $b — upload FAILED"
    echo "$out" | grep -iE 'curl:|refused|timed out|cannot|denied' | head -2 | sed 's/^/      /'
  fi
done
echo "→ $ok/${#sel[@]} uploaded to win-builder $QUEUE."
echo "  Results arrive by email to the Maintainer in ~30-60 min. 0 ERROR -> safe to submit to CRAN."

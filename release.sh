#!/usr/bin/env bash
# Cut a release: tag, push, GitHub release, and let Zenodo mint the DOI.
#
# WHY THIS EXISTS. The documentation used to show the commands with vX.Y.Z and docs/... as
# placeholders. Both times they were run, they were run literally: once from the wrong
# directory, which tagged a different repository and made Zenodo mint a bogus DOI against a
# published project; once verbatim, which created a tag actually named "vX.Y.Z". A command
# a reader is expected to edit before running is a command that will eventually be run
# unedited. So there are no placeholders here -- the version is an argument, everything else
# is derived, and the script refuses rather than guesses.
#
#   ./release.sh 1.1.0
#
set -euo pipefail

VERSION="${1:-}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED_REMOTE="hopejsh/CognitionBioChem"

die() { printf '\n  ✗ %s\n\n' "$*" >&2; exit 1; }

[ -n "$VERSION" ] || die "usage: ./release.sh <version>   e.g. ./release.sh 1.1.0"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || die "version must look like 1.2.3, got '$VERSION'. No 'v' prefix, no placeholders."

TAG="v$VERSION"
NOTES="$REPO_DIR/docs/RELEASE_NOTES_$TAG.md"

# 1. The repository must be the one we think it is. This is the check that would have caught
#    the accident: the command was run in another project's directory.
REMOTE="$(git -C "$REPO_DIR" remote get-url origin)"
case "$REMOTE" in
  *"$EXPECTED_REMOTE"*) ;;
  *) die "origin is '$REMOTE', expected $EXPECTED_REMOTE. Wrong repository — nothing done." ;;
esac

# 2. Everything else must be in order before anything irreversible happens.
[ -f "$NOTES" ] || die "no release notes at $NOTES — write them first."
[ -z "$(git -C "$REPO_DIR" status --porcelain)" ] || die "working tree is dirty; commit first."
git -C "$REPO_DIR" rev-parse "$TAG" >/dev/null 2>&1 && die "tag $TAG already exists."
[ "$(cat "$REPO_DIR/VERSION" 2>/dev/null)" = "$VERSION" ] \
  || die "VERSION says '$(cat "$REPO_DIR/VERSION" 2>/dev/null)' but you asked for '$VERSION'."
( cd "$REPO_DIR" && ./.venv/bin/python verify_all.py >/dev/null 2>&1 ) \
  || die "verify_all.py does not pass. Not releasing a red build."

printf '\n  repository : %s\n  tag        : %s\n  notes      : %s\n\n' \
  "$REMOTE" "$TAG" "$NOTES"
read -r -p "  Publish this release? Zenodo will mint a DOI that cannot be un-minted. [y/N] " ok
[ "$ok" = "y" ] || die "aborted."

git -C "$REPO_DIR" tag -a "$TAG" -m "CognitionBioChem $TAG"
git -C "$REPO_DIR" push origin "$TAG"
gh release create "$TAG" --repo "$EXPECTED_REMOTE" \
   --title "CognitionBioChem $TAG" --notes-file "$NOTES"

cat <<DONE

  Released. Zenodo mints the DOI within a few minutes.

  Then, by hand:
    - take the new VERSION DOI from the Zenodo record
    - put it in CITATION.cff under identifiers: (the concept DOI never changes)
    - bump VERSION for the next cycle

DONE

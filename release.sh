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
# This compares VERSION to the argument you typed and NOTHING ELSE. It is not the check that
# stops a release whose citable record names the wrong version -- for one release it did not:
# VERSION read 1.1.0, CITATION.cff, codemeta.json, .zenodo.json, biotools.json, the README
# citation block and the page's Provenance tab all read 1.0.0, and `./release.sh 1.1.0` passed
# here. That gap is closed one line down, inside verify_all.py, by
# platform/check_version_stamps.py.
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

  Then, by hand. None of this is automatic, and check_version_stamps.py fails until it
  is done -- which is what tells you it is not done.

    - take the new VERSION DOI from the Zenodo record
    - append a row for it to zenodo_dois.json -- version, doi, deposited. Do this FIRST:
      it is the declaration every citation surface is then checked against, and until it
      is there the guard has nothing to hold them to and says so
    - put the same DOI in CITATION.cff under identifiers:, in biotools.json (otherID AND
      the download URL + its version), and in the README version-DOI paragraph, then
      rebuild data/dataset.json (the Provenance tab copies the block from CITATION.cff).
      The concept DOI never changes
    - ./.venv/bin/python platform/check_version_stamps.py --remote confirms the row you
      just wrote against what Zenodo says the latest version is
    - replace RELEASE-NOTE-GENERATED with RELEASE-NOTE-FROZEN at the top of
      docs/RELEASE_NOTES_v$VERSION.md -- that marker is what makes this version count as
      published, here and in check_version_stamps.py
    - remove the "is not yet deposited" disclosure sentence from the surfaces that carry
      it (./.venv/bin/python platform/check_version_stamps.py names every one)
    - if you keep reading copies, rebuild them from your own working tree: their version
      stamps come from CITATION.cff, and the generators that write them are not published
      here, so this step has nothing to do with a clone
    - bump VERSION for the next cycle, then re-add the disclosure for the new version

DONE

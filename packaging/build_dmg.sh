#!/usr/bin/env bash
# packaging/build_dmg.sh
set -euo pipefail

VERSION="${1:?Usage: build_dmg.sh <version> <arch>}"
ARCH="${2:?Usage: build_dmg.sh <version> <arch>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Building chem4all.app for ${ARCH}, version ${VERSION}"

pip install --quiet pyinstaller pyinstaller-hooks-contrib
pyinstaller packaging/chem4all.spec --clean --noconfirm --distpath dist --workpath build

APP_PATH="dist/chem4all.app"
FRAMEWORKS_DIR="${APP_PATH}/Contents/Frameworks"
CAIRO_LIB_SRC="$(brew --prefix cairo)/lib/libcairo.2.dylib"
CAIRO_LIB_NAME="$(basename "${CAIRO_LIB_SRC}")"
CAIRO_LIB_BUNDLED="${FRAMEWORKS_DIR}/${CAIRO_LIB_NAME}"

echo "Copying cairo into the app bundle..."
mkdir -p "${FRAMEWORKS_DIR}"
cp -L "${CAIRO_LIB_SRC}" "${CAIRO_LIB_BUNDLED}"
install_name_tool -id "@executable_path/../Frameworks/${CAIRO_LIB_NAME}" "${CAIRO_LIB_BUNDLED}"

echo "Bundling cairo's transitive dependencies..."
dylibbundler -of -b \
  -x "${APP_PATH}/Contents/MacOS/chem4all" \
  -x "${CAIRO_LIB_BUNDLED}" \
  -d "${FRAMEWORKS_DIR}" \
  -p "@executable_path/../Frameworks"

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  echo "Codesigning bundled dylibs individually..."
  find "${APP_PATH}/Contents/Frameworks" -name "*.dylib" -print0 \
    | while IFS= read -r -d '' dylib; do
        codesign --force --sign "${CODESIGN_IDENTITY}" --options runtime "${dylib}"
      done

  echo "Codesigning app bundle..."
  codesign --force --deep --options runtime \
    --entitlements packaging/entitlements.plist \
    --sign "${CODESIGN_IDENTITY}" "${APP_PATH}"
else
  echo "CODESIGN_IDENTITY not set — producing an unsigned build for local testing."
fi

DMG_NAME="chem4all-${VERSION}-${ARCH}.dmg"
echo "Creating ${DMG_NAME}..."
hdiutil create -volname "chem4all" -srcfolder "${APP_PATH}" -ov -format UDZO "${DMG_NAME}"

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  codesign --force --sign "${CODESIGN_IDENTITY}" "${DMG_NAME}"
fi

echo "Built ${DMG_NAME}"

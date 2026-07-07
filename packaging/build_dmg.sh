#!/usr/bin/env bash
# packaging/build_dmg.sh
set -euo pipefail

VERSION="${1:?Usage: build_dmg.sh <version> <arch>}"
ARCH="${2:?Usage: build_dmg.sh <version> <arch>}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Building chem4all.app for ${ARCH}, version ${VERSION}"

BUILD_DIR="packaging/build"
rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

pip install --quiet pyinstaller pyinstaller-hooks-contrib
CHEM4ALL_VERSION="${VERSION}" pyinstaller packaging/chem4all.spec --clean --noconfirm --distpath "${BUILD_DIR}/dist" --workpath "${BUILD_DIR}/work"

APP_PATH="${BUILD_DIR}/dist/chem4all.app"
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

NOTARIZE_ARGS=()
if [ -n "${APPLE_API_KEY_PATH:-}" ]; then
  NOTARIZE_ARGS=(--key "${APPLE_API_KEY_PATH}" --key-id "${APPLE_API_KEY_ID}" --issuer "${APPLE_API_ISSUER}")

  echo "Notarizing app bundle..."
  APP_ZIP_DIR="$(mktemp -d)"
  APP_ZIP="${APP_ZIP_DIR}/chem4all.app.zip"
  ditto -c -k --keepParent "${APP_PATH}" "${APP_ZIP}"
  xcrun notarytool submit "${APP_ZIP}" "${NOTARIZE_ARGS[@]}" --wait
  xcrun stapler staple "${APP_PATH}"
fi

DMG_NAME="chem4all-${VERSION}-${ARCH}.dmg"
DMG_PATH="${BUILD_DIR}/${DMG_NAME}"
DMG_STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "${DMG_STAGING_DIR}" "${APP_ZIP_DIR:-}"' EXIT

echo "Staging dmg contents..."
ditto "${APP_PATH}" "${DMG_STAGING_DIR}/chem4all.app"
ln -s /Applications "${DMG_STAGING_DIR}/Applications"

echo "Creating ${DMG_NAME}..."
rm -f "${DMG_PATH}"
hdiutil create -volname "chem4all" -srcfolder "${DMG_STAGING_DIR}" -ov -format UDZO "${DMG_PATH}"

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
  codesign --force --sign "${CODESIGN_IDENTITY}" "${DMG_PATH}"
fi

if [ -n "${APPLE_API_KEY_PATH:-}" ]; then
  echo "Notarizing dmg..."
  xcrun notarytool submit "${DMG_PATH}" "${NOTARIZE_ARGS[@]}" --wait
  xcrun stapler staple "${DMG_PATH}"
fi

echo "Built ${DMG_PATH}"

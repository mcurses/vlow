#!/usr/bin/env bash
# Create the local code-signing certificate that scripts/build-app-bundle.sh
# uses for the development vlow.app.
#
# Why a certificate at all, when the dev bundle could be ad-hoc signed? An
# ad-hoc signature has no identity, so the designated requirement macOS stores
# is a bare cdhash of the binary:
#
#     designated => cdhash H"9597189d..."
#
# TCC pins the Microphone and Accessibility grants to that requirement, so the
# grants silently stop applying the moment the binary's bytes change — which
# happens on every `brew upgrade python@3.12`, because the bundle executable is
# a copy of Homebrew's python. vlow then runs with a live hotkey that cannot
# type and a microphone that cannot record, and nothing in Privacy & Security
# looks wrong: the toggle is still on.
#
# Signing with a stable certificate makes the requirement identity-based:
#
#     designated => identifier "com.vlow" and certificate leaf = H"873679da..."
#
# which keeps matching across rebuilds and python upgrades, so the grants are
# approved once and stay approved.
#
# This is a development convenience. Release builds are signed by
# scripts/build-release.sh with VLOW_SIGN_IDENTITY (a real Developer ID).

set -euo pipefail

CERT_NAME="${VLOW_DEV_SIGN_IDENTITY:-vlow dev signing}"
KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

if security find-identity -p codesigning | grep -q "\"$CERT_NAME\""; then
  echo "Certificate \"$CERT_NAME\" already exists — nothing to do."
  exit 0
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Generating a self-signed code-signing certificate: $CERT_NAME"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "$WORK/key.pem" -out "$WORK/cert.pem" \
  -subj "/CN=$CERT_NAME" \
  -addext "basicConstraints=critical,CA:false" \
  -addext "keyUsage=critical,digitalSignature" \
  -addext "extendedKeyUsage=critical,codeSigning" 2>/dev/null

# macOS `security` cannot read the PKCS#12 defaults that OpenSSL 3+ writes, so
# pin the legacy algorithms. The passphrase is not a secret — it only has to
# survive the few lines between export and import — but it cannot be empty:
# OpenSSL and Security disagree on how an empty PKCS#12 password is encoded,
# and the import fails with a misleading "MAC verification failed".
P12_PASS="vlowdev"
openssl pkcs12 -export -legacy \
  -certpbe PBE-SHA1-3DES -keypbe PBE-SHA1-3DES -macalg sha1 \
  -inkey "$WORK/key.pem" -in "$WORK/cert.pem" \
  -name "$CERT_NAME" -passout "pass:$P12_PASS" -out "$WORK/bundle.p12" 2>/dev/null

# -A lets codesign use the key without a keychain dialog on every build.
security import "$WORK/bundle.p12" -k "$KEYCHAIN" -P "$P12_PASS" \
  -T /usr/bin/codesign -A

echo
echo "Imported into $KEYCHAIN."
echo "macOS may ask once for permission to use the key — answer \"Always Allow\"."
echo
echo "The certificate is self-signed, so \`security find-identity -v\` lists it as"
echo "untrusted. That is expected and does not matter here: the requirement TCC"
echo "stores compares the leaf certificate's hash, which needs no chain of trust,"
echo "and locally signed binaries launch without one."
echo
echo "Next: scripts/dev-install.sh, then re-approve vlow once under"
echo "System Settings > Privacy & Security > Accessibility and > Microphone."

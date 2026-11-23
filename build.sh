#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "macOS: $(sw_vers -productVersion)"
echo "Xcode: $(xcodebuild -version | tr '\n' ' ')"
free_gb=$(df -g / | awk 'NR==2 {print $4}')
echo "Free disk: ${free_gb} GB"
if [ "$free_gb" -lt 40 ]; then
  echo "Need at least 40 GB free on the system disk."
  exit 1
fi

cd "$HOME"
if [ ! -d Telegram-iOS/.git ]; then
  git clone --recursive -j8 https://github.com/TelegramMessenger/Telegram-iOS.git
fi
cd Telegram-iOS
git submodule update --init --recursive

python3 "$ROOT/apply_metagram.py" "$HOME/Telegram-iOS"

python3 build-system/Make/ImportCertificates.py --path build-system/fake-codesigning/certs
python3 -u build-system/Make/Make.py \
  --cacheDir="$HOME/telegram-bazel-cache" \
  build \
  --configurationPath=build-system/appstore-configuration.json \
  --codesigningInformationPath=build-system/fake-codesigning \
  --configuration=release_arm64 \
  --buildNumber=100001

shopt -s nullglob
ipas=(bazel-out/applebin_ios-ios_arm*-opt-ST-*/bin/Telegram/Telegram.ipa)
if [ ${#ipas[@]} -eq 0 ]; then
  echo "Build finished, but Telegram.ipa was not found."
  exit 1
fi
cp "${ipas[0]}" "$HOME/Desktop/MetaGram.ipa"
echo "Ready: $HOME/Desktop/MetaGram.ipa"

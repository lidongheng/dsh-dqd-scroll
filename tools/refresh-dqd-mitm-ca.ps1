$ErrorActionPreference = 'Stop';

$adbPath = 'C:\leidian\LDPlayer14\adb.exe';
$device = 'emulator-5556';
$caPath = Join-Path $env:USERPROFILE '.mitmproxy\mitmproxy-ca-cert.pem';
# Refuse to mount a rotated CA until its device staging and subject hash are refreshed deliberately.
$expectedDerSha256 = 'C585B231C84C5086FB26874E5CD8065351FAC3BC12D60A8ED41AF98F17A9FF9F';

if (-not (Test-Path -LiteralPath $adbPath -PathType Leaf)) {
    throw 'LDPlayer ADB was not found at C:\leidian\LDPlayer14\adb.exe.';
}

if (-not (Test-Path -LiteralPath $caPath -PathType Leaf)) {
    throw "mitmproxy CA certificate was not found at $caPath.";
}

$caPem = [System.IO.File]::ReadAllText($caPath);
$caBase64 = $caPem -replace '-----BEGIN CERTIFICATE-----', '' -replace '-----END CERTIFICATE-----', '' -replace '\s', '';
$caDer = [Convert]::FromBase64String($caBase64);
$sha256 = [System.Security.Cryptography.SHA256]::Create();
$caDerSha256 = [BitConverter]::ToString($sha256.ComputeHash($caDer)).Replace('-', '');
$sha256.Dispose();

if ($caDerSha256 -ne $expectedDerSha256) {
    throw "The mitmproxy CA changed (DER SHA-256: $caDerSha256). Refresh the staged CA deliberately before using this script.";
}

$deviceState = & $adbPath -s $device get-state;
if ($LASTEXITCODE -ne 0 -or [string]::Join('', $deviceState).Trim() -ne 'device') {
    throw "LDPlayer device $device is not online.";
}

$rootState = & $adbPath -s $device shell "su -c 'id -u'";
if ($LASTEXITCODE -ne 0 -or [string]::Join('', $rootState).Trim() -ne '0') {
    throw "Root access is unavailable on $device.";
}

$derPath = Join-Path $env:TEMP 'dqd-mitmproxy-ca-current.der';
$shellPath = Join-Path $env:TEMP 'dqd-mitmproxy-ca-refresh.sh';
[System.IO.File]::WriteAllBytes($derPath, $caDer);

$shellScript = @'
#!/system/bin/sh
set -eu;
CERT=/data/local/tmp/codex-mitm-c8750f0d.0;
STORE=/data/local/tmp/codex-mitm-ca-c8750f0d;
APEX=/apex/com.android.conscrypt/cacerts;
SYSTEM=/system/etc/security/cacerts;
# Android drops these namespace bind mounts on reboot; boot_id prevents duplicate mounts within one boot.
MARKER=/data/local/tmp/codex-mitm-ca-c8750f0d.boot-id;
BOOT_ID="$(cat /proc/sys/kernel/random/boot_id)";

[ "$(id -u)" = 0 ] || { echo 'Root access is required'; exit 1; };
[ -f "$CERT" ] || { echo 'Current mitmproxy CA DER file is missing'; exit 1; };
[ -f "$STORE/c8750f0d.0" ] || { echo 'Staged Android CA file is missing'; exit 1; };
cmp -s "$CERT" "$STORE/c8750f0d.0" || { echo 'Staged CA does not match the current mitmproxy CA'; exit 1; };

if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$BOOT_ID" ]; then
  ZPIDS="$(pidof zygote 2>/dev/null || true) $(pidof zygote64 2>/dev/null || true)";
  for Z in $ZPIDS; do
    nsenter --mount="/proc/$Z/ns/mnt" -- cmp -s "$CERT" "$APEX/c8750f0d.0" || { echo 'Boot marker exists but zygote CA verification failed'; exit 1; };
  done;
  echo 'SYSTEM_CA_ALREADY_READY_THIS_BOOT';
  exit 0;
fi;

ZPIDS="$(pidof zygote 2>/dev/null || true) $(pidof zygote64 2>/dev/null || true)";
[ -n "$(echo "$ZPIDS" | tr -d ' ')" ] || { echo 'No zygote process found; wait for Android to finish booting'; exit 1; };
PIDS="$$ $ZPIDS";
for Z in $ZPIDS; do
  CHILDREN="$(ps -A -o PID,PPID | awk -v parent="$Z" '$2 == parent {print $1}')";
  PIDS="$PIDS $CHILDREN";
done;

SEEN=' ';
COUNT=0;
FAILED=0;
for P in $PIDS; do
  NS="$(readlink "/proc/$P/ns/mnt" 2>/dev/null || true)";
  [ -n "$NS" ] || continue;
  case "$SEEN" in *" $NS "*) continue ;; esac;
  SEEN="$SEEN$NS ";

  if nsenter --mount="/proc/$P/ns/mnt" -- cmp -s "$CERT" "$APEX/c8750f0d.0"; then
    COUNT=$((COUNT+1));
  elif nsenter --mount="/proc/$P/ns/mnt" -- /system/bin/sh -c "mount --bind '$STORE' '$SYSTEM' && mount --bind '$STORE' '$APEX' && cmp -s '$CERT' '$APEX/c8750f0d.0'"; then
    COUNT=$((COUNT+1));
  else
    FAILED=$((FAILED+1));
    echo "Namespace configuration failed for PID $P";
  fi;
done;

echo "Configured mount namespaces: $COUNT; failures: $FAILED";
[ "$FAILED" = 0 ] || exit 1;
for Z in $ZPIDS; do
  nsenter --mount="/proc/$Z/ns/mnt" -- cmp -s "$CERT" "$APEX/c8750f0d.0";
done;
printf '%s\n' "$BOOT_ID" > "$MARKER";
echo 'SYSTEM_CA_READY_THIS_BOOT';
'@;

[System.IO.File]::WriteAllText($shellPath, $shellScript, [System.Text.Encoding]::ASCII);

try {
    & $adbPath -s $device push $derPath '/data/local/tmp/codex-mitm-c8750f0d.0';
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to stage the current mitmproxy CA on LDPlayer.';
    }

    & $adbPath -s $device push $shellPath '/data/local/tmp/codex-mitm-refresh.sh';
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to stage the CA refresh script on LDPlayer.';
    }

    & $adbPath -s $device shell "su -c 'sh /data/local/tmp/codex-mitm-refresh.sh'";
    if ($LASTEXITCODE -ne 0) {
        throw 'The Android CA mount update failed; see the device output above.';
    }
}
finally {
    Remove-Item -LiteralPath $derPath -Force -ErrorAction SilentlyContinue;
    Remove-Item -LiteralPath $shellPath -Force -ErrorAction SilentlyContinue;
}

# ==================== Destiny 2 "No Hitch" Fully Silent Script ====================
# Target PC: High-end (i5/Ryzen 5+, RTX 30xx/40xx, 32GB+, NVMe)

# ----------------------- Auto-elevate -----------------------
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(`
    [Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Start-Process powershell "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# ----------------------- Paths -----------------------
$local        = $env:LOCALAPPDATA
$bungieSaved  = Join-Path $local "Bungie.net\Destiny 2"
$fnConfigPath = Join-Path $bungieSaved "cvars"
$fnCachePath  = Join-Path $bungieSaved "Cache"
$tempDirs     = @($fnCachePath)
$iniFile      = Join-Path $fnConfigPath "defaultcvars.ini"

# ----------------------- Stop Destiny 2 -----------------------
Get-Process "Destiny2" -ErrorAction SilentlyContinue | Stop-Process -Force

# ----------------------- Clear caches -----------------------
foreach ($p in $tempDirs) { if (Test-Path $p) { Remove-Item $p -Force -Recurse -ErrorAction SilentlyContinue } }

# ----------------------- Disable Game Bar / Captures -----------------------
reg add "HKCU\System\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d 0 /f | Out-Null
reg add "HKCU\System\GameConfigStore" /v GameDVR_FSEBehaviorMode /t REG_DWORD /d 2 /f | Out-Null
reg add "HKCU\SOFTWARE\Microsoft\GameBar" /v ShowStartupPanel /t REG_DWORD /d 0 /f | Out-Null
reg add "HKCU\SOFTWARE\Microsoft\GameBar" /v Enabled /t REG_DWORD /d 0 /f | Out-Null

# ----------------------- Enable HAGS -----------------------
reg add "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v HwSchMode /t REG_DWORD /d 2 /f | Out-Null

# ----------------------- Ultimate Performance plan -----------------------
powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>$null
$ult = (powercfg -list) -match "Ultimate Performance"
if ($ult) { powercfg -setactive e9a42b02-d5df-448d-aa00-03f14749eb61 }

# ----------------------- Disable Fullscreen Optimizations -----------------------
function Set-FSOFF($exePath) {
    if (-not (Test-Path $exePath)) { return }
    $regPath = "HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    reg add $regPath /v $exePath /t REG_SZ /d "~ DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE" /f | Out-Null
}

$likelyRoots = @(
    "$env:PROGRAMFILES\Bungie\Destiny 2",
    "$env:PROGRAMFILES(X86)\Bungie\Destiny 2"
)
$exe = $null
foreach ($root in $likelyRoots) {
    $candidate = Join-Path $root "Destiny2.exe"
    if (Test-Path $candidate) { $exe = $candidate; break }
}
if (-not $exe) {
    $exe = Get-ChildItem -Path "$env:SystemDrive\" -Filter "Destiny2.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if ($exe) { Set-FSOFF $exe }

# ----------------------- Destiny 2 config (low-stutter) -----------------------
if (-not (Test-Path $fnConfigPath)) { New-Item -ItemType Directory -Path $fnConfigPath -Force | Out-Null }
$iniContent = @"
cl_vsync 0
r_displayrefresh 240
g_force_high_performance_GPU 1
r_ShadowQuality 0
r_TextureQuality 2
r_EffectsQuality 0
r_PostProcessQuality 0
r_FoliageQuality 0
r_AntiAliasingQuality 0
"@
Set-Content -Path $iniFile -Value $iniContent -Encoding UTF8

# ----------------------- NVIDIA Profile Inspector (NPI) -----------------------
$work    = Join-Path $env:TEMP "D2_NPI"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$npiZip  = Join-Path $work "npi.zip"
$npiExe  = Join-Path $work "nvidiaProfileInspector.exe"
$nipPath = Join-Path $work "Destiny2_LowLatency.nip"

$nip = @"
<?xml version="1.0" encoding="utf-16"?>
<profileInspector>
  <profiles>
    <profile name="Destiny 2" description="">
      <applications>
        <application executable="Destiny2.exe" />
      </applications>
      <settings>
        <setting id="0x000000F4" valueHex="0x00000001" />
        <setting id="0x0005F543" valueHex="0x00000001" />
        <setting id="0x00A879CF" valueHex="0x00000000" />
        <setting id="0x00B66E1C" valueHex="0x00000002" />
      </settings>
    </profile>
  </profiles>
</profileInspector>
"@
$nip | Out-File -FilePath $nipPath -Encoding UTF8

function Get-LatestNpiZipUrl {
    try {
        $api = "https://api.github.com/repos/Orbmu2k/nvidiaProfileInspector/releases/latest"
        $resp = Invoke-RestMethod -Uri $api -UseBasicParsing
        $asset = $resp.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
        return $asset.browser_download_url
    } catch { return $null }
}

$zipUrl = Get-LatestNpiZipUrl
if ($zipUrl) { try { Invoke-WebRequest -Uri $zipUrl -OutFile $npiZip -UseBasicParsing } catch {} }

if (-not (Test-Path $npiZip)) {
    $fallback = "https://github.com/Orbmu2k/nvidiaProfileInspector/releases/download/2.4.0.19/nvidiaProfileInspector.zip"
    try { Invoke-WebRequest -Uri $fallback -OutFile $npiZip -UseBasicParsing } catch {}
}

$importOk = $false
if (Test-Path $npiZip) {
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($npiZip, $work, $true)
        if (Test-Path $npiExe) {
            $p = Start-Process -FilePath $npiExe -ArgumentList ("-silentImport `"$nipPath`"") -PassThru -WindowStyle Hidden
            $p.WaitForExit()
            if ($p.ExitCode -eq 0) { $importOk = $true }
        }
    } catch {}
}

# ----------------------- Summary -----------------------
Write-Host ""
Write-Host "==================== DESTINY 2 NO-HITCH RESULTS ====================" -ForegroundColor Cyan
Write-Host "INI applied: $iniFile"
if ($exe) { Write-Host "Fullscreen Optimizations disabled for: $exe" }
Write-Host "HAGS enabled, Game Bar/Captures disabled."
if ($ult) { Write-Host "Power Plan set to: Ultimate Performance" }
if ($importOk) { Write-Host "NVIDIA Profile imported successfully." }
Write-Host "================================================="
Write-Host "Reboot your PC to finalize registry + power plan changes."
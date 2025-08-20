# ==================== Fortnite "No Hitch" Super Script ====================
# Target PC: i5-9700K / RTX 3070 / 32GB DDR4 / NVMe / 1080p 240Hz
# What it does:
# 1) Kills Fortnite, clears caches (DX/NVIDIA/UE), disables Xbox Game Bar/Captures
# 2) Enables Hardware-accelerated GPU scheduling (HAGS)
# 3) Sets Power plan to Ultimate Performance (if available)
# 4) Disables Fullscreen Optimizations for the Fortnite EXE (found automatically)
# 5) Drops a minimal-hitch Fortnite GameUserSettings.ini (low latency, stable pacing)
# 6) Downloads NVIDIA Profile Inspector & silently imports a low-latency profile
# 7) Prints any step that needs your review

# ----------------------- Admin check -----------------------
If (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(`
    [Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Please run as Administrator." -ForegroundColor Red
    exit 1
}

# ----------------------- Paths -----------------------
$local = $env:LOCALAPPDATA
$fnSaved      = Join-Path $local "FortniteGame\Saved"
$fnConfigPath = Join-Path $fnSaved "Config\WindowsClient"
$fnCachePath  = Join-Path $fnSaved "Cache"
$iniFile      = Join-Path $fnConfigPath "GameUserSettings.ini"

# Shader caches (clearing stale cache helps hitching)
$dxCache     = Join-Path $local "D3DSCache"
$nvdxCache   = Join-Path $local "NVIDIA\DXCache"
$nvglCache   = Join-Path $local "NVIDIA\GLCache"
$tempDirs    = @($dxCache, $nvdxCache, $nvglCache, $fnCachePath)

# ----------------------- Stop Fortnite -----------------------
Get-Process "FortniteClient-Win64-Shipping" -ErrorAction SilentlyContinue | Stop-Process -Force

# ----------------------- Clear caches -----------------------
foreach ($p in $tempDirs) {
    if (Test-Path $p) {
        try { Remove-Item $p -Force -Recurse -ErrorAction Stop } catch {}
    }
}

# ----------------------- Disable Game Bar/Captures -----------------------
reg add "HKCU\System\GameConfigStore" /v GameDVR_Enabled /t REG_DWORD /d 0 /f | Out-Null
reg add "HKCU\System\GameConfigStore" /v GameDVR_FSEBehaviorMode /t REG_DWORD /d 2 /f | Out-Null
reg add "HKCU\System\GameConfigStore" /v GameDVR_HonorUserFSEBehaviorMode /t REG_DWORD /d 1 /f | Out-Null
reg add "HKCU\System\GameConfigStore" /v GameDVR_DSEBehavior /t REG_DWORD /d 2 /f | Out-Null
reg add "HKCU\SOFTWARE\Microsoft\GameBar" /v ShowStartupPanel /t REG_DWORD /d 0 /f | Out-Null
reg add "HKCU\SOFTWARE\Microsoft\GameBar" /v Enabled /t REG_DWORD /d 0 /f | Out-Null

# ----------------------- Enable HAGS -----------------------
reg add "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v HwSchMode /t REG_DWORD /d 2 /f | Out-Null

# ----------------------- Ultimate Performance plan -----------------------
# (Improves boost residency; skip if not supported)
powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61 2>$null
$ult = (powercfg -list) -match "Ultimate Performance"
if ($ult) { powercfg -setactive e9a42b02-d5df-448d-aa00-03f14749eb61 }

# ----------------------- Fortnite EXE: disable Fullscreen Optimizations -----------------------
function Set-FSOFF($exePath) {
    if (-not (Test-Path $exePath)) { return }
    $regPath = "HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    reg add $regPath /v $exePath /t REG_SZ /d "~ DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE" /f | Out-Null
}
# Try to find FortniteClient-Win64-Shipping.exe
$likelyRoots = @(
    "$env:PROGRAMFILES\Epic Games\Fortnite\FortniteGame\Binaries\Win64",
    "$env:PROGRAMFILES(X86)\Epic Games\Fortnite\FortniteGame\Binaries\Win64"
)
$exe = $null
foreach ($root in $likelyRoots) {
    $candidate = Join-Path $root "FortniteClient-Win64-Shipping.exe"
    if (Test-Path $candidate) { $exe = $candidate; break }
}
if (-not $exe) {
    # Wider search (capped to system drive for speed)
    $exe = Get-ChildItem -Path "$env:SystemDrive\" -Filter "FortniteClient-Win64-Shipping.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if ($exe) { Set-FSOFF $exe }

# ----------------------- Fortnite config (stutter-minimized) -----------------------
if (-not (Test-Path $fnConfigPath)) {
    New-Item -ItemType Directory -Path $fnConfigPath -Force | Out-Null
}
$iniContent = @"
[/Script/FortniteGame.FortGameUserSettings]
bUseVSync=False
bShowFPS=True
FullscreenMode=0
PreferredFullscreenMode=0
bUseDynamicResolution=False
FrameRateLimit=240.000000
# DX12 is recommended for smooth frame pacing on 30xx
# (Fortnite stores renderer separately; set DX12 in-game once; this INI focuses on scalability)

[ScalabilityGroups]
sg.ViewDistanceQuality=0
sg.ShadowQuality=0
sg.AntiAliasingQuality=0
sg.TextureQuality=2    ; Medium textures to avoid streaming hitches
sg.EffectsQuality=0
sg.PostProcessQuality=0
sg.FoliageQuality=0
sg.ShadingQuality=0

[/Script/Engine.GameUserSettings]
bUseHDRDisplayOutput=False
HDRDisplayOutputNits=1000
"@
Set-Content -Path $iniFile -Value $iniContent -Encoding UTF8

# ----------------------- NVIDIA Profile Inspector (NPI) automation -----------------------
# Official GitHub releases (Orbmu2k). We’ll grab the latest .zip we can find and silently import a .nip profile.
# If the silent import fails (driver version differences), we’ll launch NPI for manual Apply Changes.

$work = Join-Path $env:TEMP "NPI_Auto"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$npiZip = Join-Path $work "npi.zip"
$npiExe = Join-Path $work "nvidiaProfileInspector.exe"
$nipPath = Join-Path $work "Fortnite_LowLatency.nip"

# Minimal .NIP targeting Fortnite profile: Prefer Max Perf, Low Latency ON, VSync Off, Texture Filtering High Performance
# Note: .nip uses driver setting IDs. This profile sets only broadly supported ones for best compatibility.
# If import fails, we fall back to manual steps (script will tell you).
$nip = @"
<?xml version="1.0" encoding="utf-16"?>
<profileInspector>
  <profiles>
    <profile name="Fortnite" description="" save="" restore="">
      <applications>
        <application executable="FortniteClient-Win64-Shipping.exe" />
      </applications>
      <settings>
        <!-- Power management mode: Prefer maximum performance -->
        <setting id="0x000000F4" valueHex="0x00000001" /> 
        <!-- Low Latency Mode: 1 = On (try Ultra in-game via Reflex) -->
        <setting id="0x0005F543" valueHex="0x00000001" />
        <!-- Vertical Sync: Force Off -->
        <setting id="0x00A879CF" valueHex="0x00000000" />
        <!-- Texture filtering - Quality: High Performance -->
        <setting id="0x00B66E1C" valueHex="0x00000002" />
      </settings>
    </profile>
  </profiles>
</profileInspector>
"@
# Write NIP to disk
$nip | Out-File -FilePath $nipPath -Encoding UTF8

function Get-LatestNpiZipUrl {
    try {
        $api = "https://api.github.com/repos/Orbmu2k/nvidiaProfileInspector/releases/latest"
        $resp = Invoke-RestMethod -Uri $api -UseBasicParsing
        $asset = $resp.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
        return $asset.browser_download_url
    } catch {
        return $null
    }
}

$zipUrl = Get-LatestNpiZipUrl
if ($zipUrl) {
    try { Invoke-WebRequest -Uri $zipUrl -OutFile $npiZip -UseBasicParsing } catch {}
}

# Fallback to a known tag if latest API fails (keep script robust)
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
            # Silent import; supported by NPI (-silentImport). If this errors, we’ll guide manual apply.
            $p = Start-Process -FilePath $npiExe -ArgumentList ("-silentImport `"$nipPath`"") -PassThru -WindowStyle Hidden
            $p.WaitForExit()
            if ($p.ExitCode -eq 0) { $importOk = $true }
        }
    } catch {}
}

# ----------------------- Final notes -----------------------
Write-Host ""
Write-Host "==================== RESULTS ====================" -ForegroundColor Cyan
Write-Host "Fortnite INI applied: $iniFile"
if ($exe) { Write-Host "Fullscreen Optimizations disabled for: $exe" }
Write-Host "HAGS enabled, Game Bar/Captures disabled."
if ($ult) { Write-Host "Power Plan set to: Ultimate Performance" }
if ($importOk) {
    Write-Host "NVIDIA Profile: Low-latency profile imported successfully (via NPI)."
} else {
    Write-Host "NVIDIA Profile: Silent import may have failed or NPI couldn't run." -ForegroundColor Yellow
    Write-Host "Launching NPI so you can click 'Apply changes' on the Fortnite profile..."
    if (Test-Path $npiExe) {
        Start-Process -FilePath $npiExe
        Write-Host "In NPI: select 'Fortnite' profile → confirm these:" 
        Write-Host "  • Power management mode = Prefer maximum performance"
        Write-Host "  • Low Latency Mode = On"
        Write-Host "  • Vertical Sync = Off"
        Write-Host "  • Texture filtering - Quality = High performance"
        Write-Host "(Click 'Apply changes')"
    } else {
        Write-Host "Could not download NPI automatically. You can manually grab it from GitHub (Orbmu2k) and import the .nip we saved here:"
        Write-Host "  $nipPath"
    }
}
Write-Host "================================================="
Write-Host "IMPORTANT: Reboot your PC now to finalize registry + power plan changes."
# ========================================================================
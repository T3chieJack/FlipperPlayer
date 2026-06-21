@echo off
setlocal
set "FP_SELF=%~f0"
set "FP_PS1=%TEMP%\FlipperPlayer-install-%RANDOM%-%RANDOM%.ps1"

powershell.exe -NoProfile -Command "$s=[IO.File]::ReadAllText($env:FP_SELF); $m='::FLIPPERPLAYER_POWERSHELL_PAYLOAD::'; $i=$s.LastIndexOf($m); if($i -lt 0){exit 2}; $p=$s.Substring($i+$m.Length); [IO.File]::WriteAllText($env:FP_PS1,$p,(New-Object Text.UTF8Encoding($false)))"
if errorlevel 1 (
    echo Failed to extract the installer payload.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%FP_PS1%"
set "FP_EXIT=%ERRORLEVEL%"
del /q "%FP_PS1%" >nul 2>nul

if not "%FP_EXIT%"=="0" (
    echo.
    echo Installation failed. Review the error above.
)
pause
exit /b %FP_EXIT%

::FLIPPERPLAYER_POWERSHELL_PAYLOAD::
$ErrorActionPreference = "Stop"
$latestFile = "https://raw.githubusercontent.com/T3chieJack/FlipperPlayer/main/latest.txt"
$installDir = Join-Path $env:LOCALAPPDATA "Programs\FlipperPlayer"
$stage = Join-Path $env:TEMP ("FlipperPlayer-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $stage "FlipperPlayer.zip"
$extract = Join-Path $stage "extracted"

function Find-CommandPath([string[]]$names) {
    foreach ($name in $names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function New-AppShortcut($path, $launcher, $arguments, $workingDir, $icon) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $workingDir
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = "FlipperPlayer"
    $shortcut.Save()
}

try {
    Write-Host "Installing FlipperPlayer..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $stage, $extract | Out-Null
    $downloadUrl = (& curl.exe -L -f -s $latestFile).Trim()
    if (-not $downloadUrl.StartsWith("https://")) { throw "latest.txt did not contain a valid HTTPS URL." }

    & curl.exe -L -f $downloadUrl -o $zip
    if ($LASTEXITCODE -ne 0) { throw "Download failed." }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $player = Get-ChildItem $extract -Filter "player.py" -File -Recurse | Select-Object -First 1
    if (-not $player) { throw "player.py was not found in the ZIP." }

    $python = Find-CommandPath @("py.exe", "python.exe")
    if (-not $python) { throw "Install Python 3.11 or newer from python.org, then run this again." }

    Write-Host "Installing Python packages..."
    if ([IO.Path]::GetFileName($python) -ieq "py.exe") {
        & $python -3 -m pip install --user "pygame>=2.6,<3" "Pillow>=12,<13"
    } else {
        & $python -m pip install --user "pygame>=2.6,<3" "Pillow>=12,<13"
    }
    if ($LASTEXITCODE -ne 0) { throw "Python package installation failed." }

    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    Copy-Item -Path (Join-Path $player.Directory.FullName "*") -Destination $installDir -Recurse -Force

    $pythonw = Find-CommandPath @("pyw.exe", "pythonw.exe")
    if (-not $pythonw -and [IO.Path]::GetFileName($python) -ieq "python.exe") {
        $candidate = Join-Path (Split-Path -Parent $python) "pythonw.exe"
        if (Test-Path $candidate) { $pythonw = $candidate }
    }
    if (-not $pythonw) { throw "pythonw.exe or pyw.exe was not found." }

    $playerPath = Join-Path $installDir "player.py"
    $iconPath = Join-Path $installDir "Assets\logo.ico"
    $quote = [char]34
    if ([IO.Path]::GetFileName($pythonw) -ieq "pyw.exe") {
        $arguments = "-3 $quote$playerPath$quote"
    } else {
        $arguments = "$quote$playerPath$quote"
    }

    $desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "FlipperPlayer.lnk"
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\FlipperPlayer.lnk"
    New-AppShortcut $desktop $pythonw $arguments $installDir $iconPath
    New-AppShortcut $startMenu $pythonw $arguments $installDir $iconPath

    Write-Host ""
    Write-Host "FlipperPlayer installed successfully." -ForegroundColor Green
    Write-Host "It is available on the Desktop and in Windows Search."
    Write-Host "To pin it, search for FlipperPlayer, right-click it, then select Pin to taskbar."
}
finally {
    if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}

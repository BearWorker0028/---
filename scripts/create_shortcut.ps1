$baseDir = Split-Path -Parent $PSScriptRoot
if (-not $baseDir) { $baseDir = (Get-Item -Path ".").FullName }

$desktop = [Environment]::GetFolderPath("Desktop")
if (-not $desktop -or -not (Test-Path $desktop)) {
    $desktop = Join-Path $env:USERPROFILE "Desktop"
}

$shortcutPath = Join-Path $desktop "裕珍皇 智慧冷鏈監控系統.lnk"
$targetBat = Join-Path $baseDir "start.bat"
$iconPath = Join-Path $baseDir "local_web\static\TL_logo.ico"

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($shortcutPath)
$sc.TargetPath = $targetBat
$sc.WorkingDirectory = $baseDir
$sc.Description = "裕珍皇 智慧冷鏈監控與能源管理系統 (一鍵開啟)"
if (Test-Path $iconPath) {
    $sc.IconLocation = "$iconPath,0"
}
$sc.Save()

if (Test-Path $shortcutPath) {
    Write-Host "✅ 桌面捷徑建立成功：$shortcutPath" -ForegroundColor Green
    exit 0
} else {
    Write-Host "❌ 建立捷徑失敗" -ForegroundColor Red
    exit 1
}

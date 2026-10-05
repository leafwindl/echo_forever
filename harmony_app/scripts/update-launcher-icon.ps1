$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$project = Split-Path -Parent $PSScriptRoot
$workspace = Split-Path -Parent $project
$sourcePath = Join-Path $workspace 'app\android\echo_launcher_icon_source.png'
$outputPath = Join-Path $project 'entry\src\main\resources\base\media\echo_launcher_icon.png'

$source = [System.Drawing.Image]::FromFile($sourcePath)
$output = [System.Drawing.Bitmap]::new(1024, 1024)
$graphics = [System.Drawing.Graphics]::FromImage($output)
try {
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    # Start at the crown, enlarging the face without adding padding above the hair.
    $crop = [System.Drawing.Rectangle]::new(190, 150, 640, 640)
    $destination = [System.Drawing.Rectangle]::new(0, 0, 1024, 1024)
    $graphics.DrawImage($source, $destination, $crop, [System.Drawing.GraphicsUnit]::Pixel)
    $output.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $graphics.Dispose()
    $output.Dispose()
    $source.Dispose()
}

Write-Output "Updated Harmony launcher icon: $outputPath"

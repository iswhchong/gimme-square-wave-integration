# Clone the skills repository
New-Item -ItemType Directory -Force -Path ".agent/skills"
# Download ZIP
$url = "https://github.com/sickn33/antigravity-awesome-skills/archive/refs/heads/main.zip"
$zipPath = ".agent/skills/skills.zip"
$destPath = ".agent/skills"

New-Item -ItemType Directory -Force -Path $destPath
Invoke-WebRequest -Uri $url -OutFile $zipPath

# Extract
Expand-Archive -Path $zipPath -DestinationPath $destPath -Force

# Rename/Move if needed
# The zip extracts to "antigravity-awesome-skills-main"
$extractDir = Join-Path $destPath "antigravity-awesome-skills-main"
if (Test-Path $extractDir) {
    Write-Host "Extracted to $extractDir"
    # Optional: flattening could be done here but let's leave it to keep it simple
}

# Cleanup Zip
Remove-Item -Path $zipPath

Write-Host "Skills installed successfully from ZIP."

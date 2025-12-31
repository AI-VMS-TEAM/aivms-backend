# Fresh Start Script - Create Clean Git Repository
# This script removes git history and creates a fresh repository

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  GIT FRESH START - CLEAN REPOSITORY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Warning
Write-Host "⚠️  WARNING: This will DELETE all git history!" -ForegroundColor Yellow
Write-Host "   Only the current files will remain." -ForegroundColor Yellow
Write-Host ""

# Ask for confirmation
$confirm = Read-Host "Do you want to proceed? (yes/no)"

if ($confirm -ne "yes") {
    Write-Host "❌ Cancelled. No changes made." -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "🔄 Step 1: Backing up current .git folder..." -ForegroundColor Green

# Backup .git folder
if (Test-Path ".git") {
    if (Test-Path ".git_backup") {
        Remove-Item -Path ".git_backup" -Recurse -Force
    }
    Copy-Item -Path ".git" -Destination ".git_backup" -Recurse
    Write-Host "   ✅ Backup created: .git_backup" -ForegroundColor Green
}

Write-Host ""
Write-Host "🗑️  Step 2: Removing old .git folder..." -ForegroundColor Green
Remove-Item -Path ".git" -Recurse -Force
Write-Host "   ✅ Old git history removed" -ForegroundColor Green

Write-Host ""
Write-Host "🆕 Step 3: Initializing new repository..." -ForegroundColor Green
git init
Write-Host "   ✅ New repository initialized" -ForegroundColor Green

Write-Host ""
Write-Host "📦 Step 4: Adding all files..." -ForegroundColor Green
git add .
Write-Host "   ✅ Files staged" -ForegroundColor Green

Write-Host ""
Write-Host "💾 Step 5: Creating initial commit..." -ForegroundColor Green
git commit -m "Initial commit: Clean AIVMS backend

- AI-powered video surveillance system
- YOLO11 object detection with ByteTrack
- Zone-based analytics
- HLS streaming via MediaMTX
- Automatic retention management
- Web dashboard and REST API"

Write-Host "   ✅ Initial commit created" -ForegroundColor Green

Write-Host ""
Write-Host "📊 Step 6: Checking repository size..." -ForegroundColor Green
git count-objects -vH

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ✅ FRESH START COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Yellow
Write-Host "   1. Add your GitHub remote:" -ForegroundColor White
Write-Host "      git remote add origin https://github.com/yourusername/aivms-backend.git" -ForegroundColor Gray
Write-Host ""
Write-Host "   2. Push to GitHub:" -ForegroundColor White
Write-Host "      git branch -M main" -ForegroundColor Gray
Write-Host "      git push -u origin main --force" -ForegroundColor Gray
Write-Host ""
Write-Host "   3. Verify on GitHub that repository size is ~10-50 MB" -ForegroundColor White
Write-Host ""
Write-Host "💡 Tip: If something goes wrong, restore from backup:" -ForegroundColor Yellow
Write-Host "   Remove-Item -Path .git -Recurse -Force" -ForegroundColor Gray
Write-Host "   Rename-Item -Path .git_backup -NewName .git" -ForegroundColor Gray
Write-Host ""


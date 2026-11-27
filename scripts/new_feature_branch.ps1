param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [ValidateSet("feat", "fix", "chore")]
    [string]$Type = "feat",
    [switch]$RunChecks
)

$ErrorActionPreference = "Stop"
$branch = "$Type/$Name"

Write-Host "Creating branch: $branch" -ForegroundColor Cyan
git checkout -b $branch

if ($RunChecks) {
    Write-Host "Running pytest..." -ForegroundColor Yellow
    python -m pytest tests/ -q
    Write-Host "Running visual-qa..." -ForegroundColor Yellow
    python run.py visual-qa
}

Write-Host "Branch '$branch' is ready. After committing, push with:" -ForegroundColor Green
Write-Host "  git push -u origin $branch" -ForegroundColor White

<#
.SYNOPSIS
    12321.cn scraping script - fetches complaint count and generates charts
    Runs every 2 hours from 8:00 to 22:00 via Windows Task Scheduler
#>

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8

# ============ Config ============
$projectDir    = "C:\Users\Administrator\scraper_12321"
$dataFile      = Join-Path $projectDir "data\scraped_data.csv"
$reportsDir    = Join-Path $projectDir "reports"
$templateUnified = Join-Path $projectDir "template_unified.html"
$targetUrl     = "https://www.12321.cn/"

# ============ 1. Fetch webpage ============
$logPrefix = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]"
Write-Host "$logPrefix Fetching $targetUrl"

try {
    $response = Invoke-WebRequest -Uri $targetUrl -UseBasicParsing -TimeoutSec 30
} catch {
    Write-Error "HTTP request failed: $_"
    exit 1
}

$html = $response.Content

# ============ 2. Extract complaint count ============
if ($html -match '<span\s+class="count">([\d,]+)</span>') {
    $countStr = $Matches[1]
    $count = [int]($countStr -replace ',', '')
    Write-Host "$logPrefix Extracted count: $count"
} else {
    Write-Error "Failed to extract complaint count from page"
    exit 1
}

$now       = Get-Date
$timeStr   = $now.ToString("yyyy-MM-dd HH:mm:ss")
$dateStr   = $now.ToString("yyyy-MM-dd")
$hourLabel = $now.ToString("HH:00")

# ============ 3. Save to CSV ============
if (-not (Test-Path $dataFile)) {
    # Ensure data directory exists
    $dataDir = Split-Path $dataFile -Parent
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    }
    "datetime,count" | Out-File -FilePath $dataFile -Encoding utf8
    Write-Host "$logPrefix Created data file: $dataFile"
}

"$timeStr,$count" | Out-File -FilePath $dataFile -Encoding utf8 -Append
Write-Host "$logPrefix Data saved to CSV"

# ============ 4. Read CSV data ============
$allData = Import-Csv -Path $dataFile

# Process all data with parsed fields
$allRows = $allData | ForEach-Object {
    $dt = $_.datetime
    [PSCustomObject]@{
        datetime = $dt
        date     = $dt.Substring(0, 10)
        time     = $dt.Substring(11)
        count    = [int]$_.count
    }
}

# Today's data
$todayRows = $allRows | Where-Object { $_.date -eq $dateStr }

# Daily totals: last entry per day
$dailyTotals = $allRows |
    Group-Object -Property date |
    ForEach-Object {
        $_.Group | Sort-Object -Property datetime -Descending | Select-Object -First 1
    } |
    Sort-Object -Property date

# Current month data
$currentMonth = $now.ToString("yyyy-MM")
$monthlyTotals = $dailyTotals | Where-Object { $_.date -like "$currentMonth*" }

# ============ 5. Prepare daily chart data ============
$todayLabels = @()
$todayCounts = @()
$dailyTableRows = @()
foreach ($row in $todayRows) {
    $t = $row.datetime.Substring(11, 5)
    $todayLabels += "'$t'"
    $todayCounts += $row.count
    $dailyTableRows += "<tr><td>$($row.time)</td><td>$($row.count.ToString('N0'))</td></tr>"
}

$dailyLabelsJs = $todayLabels -join ", "
$dailyCountsJs = $todayCounts -join ", "
$dailyMax = 100
$todayDataPoints = @($todayRows).Count
if (@($todayCounts).Count -gt 0) {
    $maxVal = ($todayCounts | Measure-Object -Maximum).Maximum
    $dailyMax = [Math]::Ceiling($maxVal * 1.1)
}
$dailyYmin = [Math]::Floor(($dailyMax * 0.7))

# ============ 6. Prepare monthly chart data ============
$monthLabels = @()
$monthCounts = @()
$monthTableRows = @()
foreach ($row in $monthlyTotals) {
    $day = [int]($row.date.Substring(8, 2))
    $monthLabels += "'$day'"
    $monthCounts += $row.count
    $monthTableRows += "<tr><td>$($row.date)</td><td>$($row.count.ToString('N0'))</td><td>$($row.time)</td></tr>"
}

$monthLabelsJs = $monthLabels -join ", "
$monthCountsJs = $monthCounts -join ", "
$monthMax = 100
$monthAvg = 0
$statDays = @($monthlyTotals).Count
if ($statDays -gt 0) {
    $maxVal = ($monthCounts | Measure-Object -Maximum).Maximum
    $monthMax = [Math]::Ceiling($maxVal * 1.15)
    $monthAvg = [int](($monthCounts | Measure-Object -Average).Average)
}
$monthYmin = [Math]::Floor(($monthMax * 0.5))

# Empty table fallbacks
if ($dailyTableRows.Count -eq 0) { $dailyTableRows = @('<tr><td colspan="2" class="empty">暂无数据</td></tr>') }
if ($monthTableRows.Count -eq 0) { $monthTableRows = @('<tr><td colspan="3" class="empty">暂无数据</td></tr>') }

# ============ 7. Generate unified report ============
$updateTime = $now.ToString("yyyy-MM-dd HH:mm:ss")
$template = Get-Content -Path $templateUnified -Raw -Encoding UTF8
$report = $template `
    -replace '\{\{UPDATE_TIME\}\}', $updateTime `
    -replace '\{\{DATE_STR\}\}', $dateStr `
    -replace '\{\{CURRENT_MONTH\}\}', $currentMonth `
    -replace '\{\{LATEST_COUNT\}\}', $count.ToString('N0') `
    -replace '\{\{TODAY_POINTS\}\}', $todayDataPoints `
    -replace '\{\{MONTH_DAYS\}\}', $statDays `
    -replace '\{\{MONTH_AVG\}\}', $monthAvg.ToString('N0') `
    -replace '\{\{DAILY_LABELS\}\}', $dailyLabelsJs `
    -replace '\{\{DAILY_COUNTS\}\}', $dailyCountsJs `
    -replace '\{\{DAILY_YMIN\}\}', $dailyYmin `
    -replace '\{\{DAILY_YMAX\}\}', $dailyMax `
    -replace '\{\{DAILY_TABLE_ROWS\}\}', ($dailyTableRows -join "`n") `
    -replace '\{\{MONTHLY_LABELS\}\}', $monthLabelsJs `
    -replace '\{\{MONTHLY_COUNTS\}\}', $monthCountsJs `
    -replace '\{\{MONTHLY_YMIN\}\}', $monthYmin `
    -replace '\{\{MONTHLY_YMAX\}\}', $monthMax `
    -replace '\{\{MONTHLY_TABLE_ROWS\}\}', ($monthTableRows -join "`n")

$reportPath = Join-Path $reportsDir "report.html"
$report | Out-File -FilePath $reportPath -Encoding utf8
Write-Host "$logPrefix Unified report generated: $reportPath"
Write-Host "$logPrefix Done! Complaint count: $count"

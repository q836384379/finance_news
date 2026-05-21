[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Title,

  [string]$Body,

  [string]$BodyFile,

  [string]$LinkText = "Open Link",

  [string]$LinkUrl,

  [string]$WebhookUrl = $env:FEISHU_WEBHOOK_URL,

  [string]$BotSecret = $env:FEISHU_BOT_SECRET,

  [string]$TrackingKey,

  [string]$StateFile = (Join-Path $PSScriptRoot '..\.runtime\feishu-send-state.json'),

  [int]$RetryCount = 3,

  [int]$RetryDelaySeconds = 10,

  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-StateFilePath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  try {
    return [System.IO.Path]::GetFullPath($Path)
  } catch {
    return $Path
  }
}

function Get-UserEnvFallback {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name
  )

  try {
    $value = Get-ItemProperty -Path 'HKCU:\Environment' -Name $Name -ErrorAction Stop |
      Select-Object -ExpandProperty $Name
    if (-not [string]::IsNullOrWhiteSpace($value)) {
      return $value
    }
  } catch {
    return $null
  }

  return $null
}

function Read-SendState {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    return @{}
  }

  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  if ([string]::IsNullOrWhiteSpace($raw)) {
    return @{}
  }

  $parsed = $raw | ConvertFrom-Json -AsHashtable
  if ($null -eq $parsed) {
    return @{}
  }

  return $parsed
}

function Write-SendState {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [Parameter(Mandatory = $true)]
    [hashtable]$State
  )

  $parent = Split-Path -Parent $Path
  if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
  }

  $jsonState = $State | ConvertTo-Json -Depth 10
  [System.IO.File]::WriteAllText($Path, $jsonState, [System.Text.UTF8Encoding]::new($false))
}

if ([string]::IsNullOrWhiteSpace($WebhookUrl)) {
  $WebhookUrl = Get-UserEnvFallback -Name 'FEISHU_WEBHOOK_URL'
}

if ([string]::IsNullOrWhiteSpace($BotSecret)) {
  $BotSecret = Get-UserEnvFallback -Name 'FEISHU_BOT_SECRET'
}

if ($BodyFile) {
  if (-not (Test-Path -LiteralPath $BodyFile)) {
    throw "Body file not found: $BodyFile"
  }
  $Body = Get-Content -LiteralPath $BodyFile -Raw -Encoding UTF8
}

if ([string]::IsNullOrWhiteSpace($Body)) {
  throw "Body is required. Provide -Body or -BodyFile."
}

if (-not $DryRun -and [string]::IsNullOrWhiteSpace($WebhookUrl)) {
  throw "Webhook URL is missing. Set FEISHU_WEBHOOK_URL or pass -WebhookUrl."
}

$rows = @()
$lines = $Body -split "(`r`n|`n|`r)"
foreach ($line in $lines) {
  $trimmed = $line.Trim()
  if ([string]::IsNullOrWhiteSpace($trimmed)) {
    continue
  }

  $rows += ,@(
    @{
      tag  = "text"
      text = $trimmed
    }
  )
}

if (-not [string]::IsNullOrWhiteSpace($LinkUrl)) {
  $rows += ,@(
    @{
      tag  = "a"
      text = $LinkText
      href = $LinkUrl
    }
  )
}

$payload = @{
  msg_type = "post"
  content  = @{
    post = @{
      zh_cn = @{
        title   = $Title
        content = $rows
      }
    }
  }
}

if (-not [string]::IsNullOrWhiteSpace($BotSecret)) {
  $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString()
  $keyBytes = [Text.Encoding]::UTF8.GetBytes($timestamp + "`n" + $BotSecret)
  $hmac = [System.Security.Cryptography.HMACSHA256]::new($keyBytes)
  try {
    $signBytes = $hmac.ComputeHash([byte[]]::new(0))
  } finally {
    $hmac.Dispose()
  }

  $payload.timestamp = $timestamp
  $payload.sign = [Convert]::ToBase64String($signBytes)
}

$json = $payload | ConvertTo-Json -Depth 10

if ($DryRun) {
  [pscustomobject]@{
    ok      = $true
    dry_run = $true
    payload = $payload
  } | ConvertTo-Json -Depth 10
  exit 0
}

$attempt = 0
$response = $null
$lastErrorMessage = $null

while ($attempt -lt $RetryCount) {
  $attempt += 1

  try {
    $response = Invoke-RestMethod `
      -Method Post `
      -Uri $WebhookUrl `
      -ContentType "application/json; charset=utf-8" `
      -Body $json

    $responseCode = $null
    if ($response.PSObject.Properties.Name -contains "StatusCode") {
      $responseCode = $response.StatusCode
    } elseif ($response.PSObject.Properties.Name -contains "code") {
      $responseCode = $response.code
    }

    $responseMsg = ""
    if ($response.PSObject.Properties.Name -contains "msg") {
      $responseMsg = [string]$response.msg
    } elseif ($response.PSObject.Properties.Name -contains "StatusMessage") {
      $responseMsg = [string]$response.StatusMessage
    }

    $isTransientResponse = $false
    if ($responseCode -ne 0) {
      if ($responseMsg -match "frequency limited|timeout|temporar|temporarily|rate limit") {
        $isTransientResponse = $true
      }
    }

    if (-not $isTransientResponse -or $attempt -ge $RetryCount) {
      break
    }
  } catch {
    $lastErrorMessage = $_.Exception.Message
    if ($attempt -ge $RetryCount) {
      throw
    }
  }

  Start-Sleep -Seconds ($RetryDelaySeconds * $attempt)
}

$statusCode = $null
if ($response.PSObject.Properties.Name -contains "StatusCode") {
  $statusCode = $response.StatusCode
} elseif ($response.PSObject.Properties.Name -contains "code") {
  $statusCode = $response.code
}

$ok = $false
if ($statusCode -eq 0) {
  $ok = $true
}

$statePath = Get-StateFilePath -Path $StateFile
if ($ok -and -not [string]::IsNullOrWhiteSpace($TrackingKey)) {
  $state = Read-SendState -Path $statePath
  $state[$TrackingKey] = @{
    title = $Title
    sent_at = (Get-Date).ToString("o")
    sent_date = (Get-Date).ToString("yyyy-MM-dd")
    attempts = $attempt
  }
  Write-SendState -Path $statePath -State $state
}

[pscustomobject]@{
  ok          = $ok
  title       = $Title
  attempts    = $attempt
  webhookHost = ([uri]$WebhookUrl).Host
  lastError   = $lastErrorMessage
  trackingKey = $TrackingKey
  stateFile   = $statePath
  response    = $response
} | ConvertTo-Json -Depth 10

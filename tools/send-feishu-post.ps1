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

  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

$response = Invoke-RestMethod `
  -Method Post `
  -Uri $WebhookUrl `
  -ContentType "application/json; charset=utf-8" `
  -Body $json

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

[pscustomobject]@{
  ok          = $ok
  title       = $Title
  webhookHost = ([uri]$WebhookUrl).Host
  response    = $response
} | ConvertTo-Json -Depth 10


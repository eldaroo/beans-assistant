# Script para probar el endpoint de chat simulation

$BASE_URL = "http://localhost:8000/api"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Chat Simulation API - Test Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: Simple message
Write-Host "[Test 1] Mensaje simple" -ForegroundColor Yellow
Write-Host ""

$body = @{
    phone = "+5491112345678"
    message = "cuántos productos tengo?"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "$BASE_URL/chat/simulate" -Method Post -Body $body -ContentType "application/json"

Write-Host "Phone: $($response.phone)" -ForegroundColor Gray
Write-Host "User: $($response.user_message)" -ForegroundColor Green
Write-Host "Bot: $($response.bot_response)" -ForegroundColor Cyan
Write-Host ""

# Test 2: Different tenant
Write-Host "[Test 2] Diferente tenant" -ForegroundColor Yellow
Write-Host ""

$body2 = @{
    phone = "+61476777212"
    message = "mostrame el stock"
} | ConvertTo-Json

$response2 = Invoke-RestMethod -Uri "$BASE_URL/chat/simulate" -Method Post -Body $body2 -ContentType "application/json"

Write-Host "Phone: $($response2.phone)" -ForegroundColor Gray
Write-Host "User: $($response2.user_message)" -ForegroundColor Green
Write-Host "Bot: $($response2.bot_response)" -ForegroundColor Cyan
Write-Host ""

# Test 3: Batch messages
Write-Host "[Test 3] Múltiples mensajes (batch)" -ForegroundColor Yellow
Write-Host ""

$batch = @(
    @{ phone = "+5491112345678"; message = "hola" }
    @{ phone = "+5491112345678"; message = "cuál es mi ganancia?" }
    @{ phone = "+5491112345678"; message = "gracias" }
) | ConvertTo-Json

$batchResponse = Invoke-RestMethod -Uri "$BASE_URL/chat/simulate/batch" -Method Post -Body $batch -ContentType "application/json"

foreach ($r in $batchResponse) {
    Write-Host "---" -ForegroundColor Gray
    Write-Host "User: $($r.user_message)" -ForegroundColor Green
    Write-Host "Bot: $($r.bot_response)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Tests completados!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

# Script de limpeza da codebase
# Remove arquivos de teste e temporarios

Write-Host "[CLEANUP] Limpando codebase..." -ForegroundColor Cyan

# Arquivos de teste para remover
$testFiles = @(
    "test_direct.py",
    "test_matching.py",
    "test_matching_debug.py",
    "test_single_incentive.py",
    "test_with_llm.py",
    "debug_matching.py",
    "check_ids.py",
    "check_status.py",
    "final_test.py",
    "simple_rag_test.py",
    "lightweight_rag.py"
)

# Scripts PowerShell temporários para remover
$psScripts = @(
    "descobrir_senha.ps1",
    "testar_senhas.ps1", 
    "testar_conexao.ps1",
    "1_resetar_senha.ps1",
    "2_restaurar_seguranca.ps1",
    "install.ps1",
    "setup_completo.ps1",
    "setup_final.ps1",
    "setup_supabase.ps1"
)

# Scripts Python utilitários para remover
$utilityScripts = @(
    "check_data_counts.py",
    "deep_clean_data.py",
    "fix_corrupted_data.py",
    "populate_matches.py",
    "run_matching.py"
)

# Pastas obsoletas para remover
$obsoleteDirs = @(
    "dashboard",
    "frontend",
    "venv",
    "scripts"
)

# Documentação duplicada para remover
$docFiles = @(
    "MUDAR_SENHA_PASSO_A_PASSO.md",
    "RESETAR_SENHA_SIMPLES.md",
    "INSTALAR_POSTGRESQL.md",
    "roadmap.md"
)

# Remover arquivos de teste Python
Write-Host "`n[PYTHON] Removendo arquivos de teste Python..." -ForegroundColor Yellow
foreach ($file in $testFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "  [OK] Removido: $file" -ForegroundColor Green
    }
}

# Remover scripts PowerShell temporarios
Write-Host "`n[POWERSHELL] Removendo scripts temporarios..." -ForegroundColor Yellow
foreach ($file in $psScripts) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "  [OK] Removido: $file" -ForegroundColor Green
    }
}

# Remover scripts Python utilitarios
Write-Host "`n[UTILITIES] Removendo scripts utilitarios..." -ForegroundColor Yellow
foreach ($file in $utilityScripts) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "  [OK] Removido: $file" -ForegroundColor Green
    }
}

# Remover pastas obsoletas
Write-Host "`n[FOLDERS] Removendo pastas obsoletas..." -ForegroundColor Yellow
foreach ($dir in $obsoleteDirs) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force
        Write-Host "  [OK] Removido: $dir/" -ForegroundColor Green
    }
}

# Remover documentacao duplicada
Write-Host "`n[DOCS] Removendo documentacao duplicada..." -ForegroundColor Yellow
foreach ($file in $docFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "  [OK] Removido: $file" -ForegroundColor Green
    }
}

# Limpar __pycache__
Write-Host "`n[CACHE] Limpando __pycache__..." -ForegroundColor Yellow
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "  [OK] __pycache__ removidos" -ForegroundColor Green

# Limpar CSVs descompactados (manter os .zip)
Write-Host "`n[CSV] Limpando CSVs descompactados..." -ForegroundColor Yellow
if (Test-Path "companies.csv") {
    Remove-Item "companies.csv" -Recurse -Force
    Write-Host "  [OK] Removido: companies.csv" -ForegroundColor Green
}
if (Test-Path "incentives.csv") {
    Remove-Item "incentives.csv" -Recurse -Force
    Write-Host "  [OK] Removido: incentives.csv" -ForegroundColor Green
}

# Criar pasta para documentacao
Write-Host "`n[ORGANIZE] Organizando documentacao..." -ForegroundColor Yellow
if (-not (Test-Path "docs")) {
    New-Item -ItemType Directory -Path "docs" -Force | Out-Null
}

# Mover documentacao importante para docs/
$docsToKeep = @(
    "README.md",
    "SETUP.md",
    "SUCESSO.md",
    "DATABASE_IMPLEMENTATION.md",
    "README_MATCHING.md"
)

foreach ($doc in $docsToKeep) {
    if (Test-Path $doc) {
        Copy-Item $doc "docs/" -Force
        Write-Host "  [OK] Copiado: $doc -> docs/" -ForegroundColor Green
    }
}

# Remover documentacao da raiz (mantendo apenas README.md principal)
Write-Host "`n[CLEANUP] Removendo documentacao duplicada da raiz..." -ForegroundColor Yellow
$docsToRemoveFromRoot = @(
    "DATABASE_IMPLEMENTATION.md",
    "README_MATCHING.md",
    "SETUP.md",
    "SUCESSO.md"
)

foreach ($doc in $docsToRemoveFromRoot) {
    if (Test-Path $doc) {
        Remove-Item $doc -Force
        Write-Host "  [OK] Removido da raiz: $doc (mantido em docs/)" -ForegroundColor Green
    }
}

# Resumo
Write-Host "`n[COMPLETE] Limpeza concluida!" -ForegroundColor Cyan
Write-Host "`nEstrutura final limpa:" -ForegroundColor White
Write-Host ""
Write-Host "  [DIR] core/               - Sistema RAG + Matching" -ForegroundColor Gray
Write-Host "  [DIR] database/           - Schema SQL + Import" -ForegroundColor Gray
Write-Host "  [DIR] data/               - CSVs compactados (.zip)" -ForegroundColor Gray
Write-Host "  [DIR] docs/               - Documentacao completa" -ForegroundColor Gray
Write-Host "  [DIR] chroma_db/          - Vector store (auto-criado)" -ForegroundColor Gray
Write-Host ""
Write-Host "  [FILE] streamlit_app.py   - Dashboard principal" -ForegroundColor Cyan
Write-Host "  [FILE] initialize_rag.py  - Indexar dados RAG" -ForegroundColor Cyan
Write-Host "  [FILE] README.md          - Documentacao principal" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [FILE] requirements.txt   - Dependencias Python" -ForegroundColor Gray
Write-Host "  [FILE] config.env         - Configuracoes (criar!)" -ForegroundColor Yellow
Write-Host "  [FILE] .gitignore         - Git ignore rules" -ForegroundColor Gray
Write-Host ""
Write-Host "[INFO] Arquivos removidos:" -ForegroundColor White
Write-Host "  - 11 arquivos de teste Python" -ForegroundColor DarkGray
Write-Host "  - 9 scripts PowerShell temporarios" -ForegroundColor DarkGray
Write-Host "  - 5 scripts Python utilitarios" -ForegroundColor DarkGray
Write-Host "  - 4 pastas obsoletas (dashboard, frontend, venv, scripts)" -ForegroundColor DarkGray
Write-Host "  - 8 arquivos de documentacao duplicados" -ForegroundColor DarkGray
Write-Host "  - Cache Python (__pycache__/)" -ForegroundColor DarkGray
Write-Host "  - CSVs descompactados" -ForegroundColor DarkGray

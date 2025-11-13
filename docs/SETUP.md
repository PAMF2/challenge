# Guia Completo de Instalação - Sistema de Matching RAG

## Pré-requisitos

### Software Necessário
- **Python 3.13+** - https://www.python.org/downloads/
- **PostgreSQL 15+** - https://www.postgresql.org/download/
- **Git** - https://git-scm.com/downloads
- **API Key do Google Gemini** - https://ai.google.dev/

## Instalação Passo a Passo

### 1. Clonar Repositório
```powershell
git clone <repository-url>
cd "Projeto Augusta"
```

### 2. Configurar Ambiente Python
```powershell
# Criar ambiente virtual
python -m venv .venv

# Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# Atualizar pip
python -m pip install --upgrade pip

# Instalar dependências
pip install -r requirements.txt
```

### 3. Configurar PostgreSQL

#### Iniciar PostgreSQL (Porta 5433)
```powershell
# Windows - com instalador
# Definir porta 5433 durante instalação

# Verificar serviço rodando
Get-Service postgresql*
```

#### Criar Base de Dados
```powershell
# Conectar ao PostgreSQL
psql -U postgres -p 5433

# Criar database
CREATE DATABASE incentivos_db WITH ENCODING 'UTF8';

# Sair
\q
```

#### Importar Schema
```powershell
# Importar estrutura
psql -U postgres -p 5433 -d incentivos_db -f database/schema.sql
```

### 4. Configurar Variáveis de Ambiente

Criar arquivo `config.env` na raiz do projeto:

```env
# API Key do Google Gemini
GEMINI_API_KEY=AIza...sua_key_aqui

# URL do PostgreSQL
DATABASE_URL=postgresql://postgres:sua_senha@localhost:5433/incentivos_db
```

⚠️ **Importante:** Nunca commitar `config.env` no Git!

### 5. Importar Dados

```powershell
# Descompactar CSVs
Expand-Archive companies.csv.zip
Expand-Archive incentives.csv.zip

# Importar para PostgreSQL
python database/import_data.py
```

**Tempo estimado:** 5-10 minutos para 250k empresas

### 6. Indexar Sistema RAG

```powershell
python initialize_rag.py
```

**O que acontece:**
- Indexa 880 incentivos em chunks semânticos
- Indexa 250k empresas (amostra)
- Indexa 25 matches com justificações
- Cria embeddings com sentence-transformers
- Salva em `chroma_db/`

**Tempo estimado:** 15-30 minutos

### 7. Executar Dashboard

```powershell
streamlit run streamlit_app.py
```

✅ Acesse: **http://localhost:8501**

## Verificação da Instalação

### 1. Testar Conexão PostgreSQL
```powershell
python -c "from database.import_data import test_connection; test_connection()"
```

### 2. Testar ChromaDB
```powershell
python -c "from core.rag_system import initialize_rag_system; kb, _ = initialize_rag_system('$env:DATABASE_URL', '$env:GEMINI_API_KEY'); print('OK')"
```

### 3. Testar Gemini API
```powershell
python -c "import google.generativeai as genai; import os; genai.configure(api_key=os.getenv('GEMINI_API_KEY')); model = genai.GenerativeModel('gemini-2.0-flash-exp'); print('OK')"
```

## Estrutura Final

Após instalação completa:

```
Projeto Augusta/
├── .venv/                     # Ambiente virtual Python
├── chroma_db/                 # Vector store (880 inc + 250k emp)
│   ├── incentives/           
│   ├── companies/
│   └── matches/
├── data/
│   ├── companies.csv         # Descompactado (250k linhas)
│   └── incentives.csv        # Descompactado (500 linhas)
├── config.env                # Suas credenciais
└── ...
```

## Solução de Problemas Comuns

### PostgreSQL não inicia na porta 5433
```powershell
# Verificar porta em uso
netstat -ano | findstr :5433

# Editar postgresql.conf
# port = 5433

# Reiniciar serviço
Restart-Service postgresql*
```

### Erro: "ModuleNotFoundError"
```powershell
# Verificar ambiente virtual ativo
Get-Command python | Select-Object Source
# Deve mostrar: .venv\Scripts\python.exe

# Reinstalar dependências
pip install -r requirements.txt --force-reinstall
```

### Erro: "GEMINI_API_KEY not found"
```powershell
# Verificar config.env existe
Test-Path config.env

# Recarregar variáveis
$env:GEMINI_API_KEY = (Get-Content config.env | Select-String "GEMINI_API_KEY").Line.Split("=")[1]
```

### ChromaDB muito lento
```powershell
# Indexar apenas amostra (5k empresas)
python initialize_rag.py --sample 5000
```

## Performance Esperada

### Matching (Fase 3)
- **Tempo:** 17s por incentivo
- **Custo:** $0.007 por incentivo
- **Qualidade:** Scores LLM 8-10/10

### Chatbot RAG
- **Latência:** < 6s primeira resposta
- **Custo:** $0.008 por mensagem
- **Documentos:** 30 chunks recuperados

## Próximos Passos

Após instalação:
1. ✅ Testar matching: Aba "Matching" → Selecionar incentivo
2. ✅ Testar chat: Aba "Chat" → "quais empresas de energia?"
3. ✅ Explorar estatísticas e visualizações
4. ✅ Exportar resultados em CSV

## Suporte

- 📧 Issues no GitHub
- 📚 Ver `README.md` para documentação completa
- 📖 Ver `SUCESSO.md` para casos de uso

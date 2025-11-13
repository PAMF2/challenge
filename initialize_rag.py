#!/usr/bin/env python
"""
🚀 INICIALIZAÇÃO DO SISTEMA RAG
Script para indexar dados na base de conhecimento vetorial
"""

import os
import sys
import time
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Configurar path
sys.path.append('.')

# Carregar configurações
load_dotenv('config.env')
DB_URL = os.getenv('DATABASE_URL')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

def initialize_rag_database():
    """Inicializar e indexar base de conhecimento RAG"""
    
    print("🚀 INICIALIZANDO SISTEMA RAG")
    print("=" * 50)
    
    try:
        # Importar sistema RAG
        from core.rag_system import initialize_rag_system
        from database.matching_service import DatabaseMatchingService
        
        # Inicializar sistema RAG
        print("📚 Criando base de conhecimento...")
        kb, chatbot = initialize_rag_system(DB_URL, GEMINI_API_KEY)
        
        # Verificar estado atual
        try:
            incentives_count = kb.collections['incentives'].count()
            companies_count = kb.collections['companies'].count()
            matches_count = kb.collections['matches'].count()

            print(f"📊 Estado atual:")
            print(f"   - Incentivos: {incentives_count}")
            print(f"   - Empresas: {companies_count}")
            print(f"   - Matches: {matches_count}")

            force_reindex = os.getenv('RAG_FORCE_REINDEX', '').lower() in {'1', 'true', 'yes'}

            expected_min_incentives = 800  # esperamos múltiplos chunks por incentivo
            expected_min_companies = 200_000  # todas as empresas devem ser indexadas
            expected_min_matches = 1  # pelo menos um match quando já populado

            needs_reindex = (
                incentives_count < expected_min_incentives
                or companies_count < expected_min_companies
                or matches_count < expected_min_matches
            )

            if not needs_reindex and not force_reindex:
                print("✅ Base completamente indexada!")
                return kb, chatbot

            if force_reindex:
                print("⚠️ Reindexação forçada via RAG_FORCE_REINDEX")
            else:
                print("⚠️ Base incompleta - reindexando...")

        except Exception as e:
            print(f"⚠️ Erro ao verificar estado: {e}")
        
        # Carregar dados da base com SQLAlchemy
        print("📊 Carregando dados da base...")
        
        # Criar engine SQLAlchemy para pandas
        db_engine = create_engine(DB_URL)
        
        # Carregar incentivos
        print("   📋 Carregando incentivos...")
        incentives_query = "SELECT * FROM incentives"
        incentives_df = pd.read_sql(incentives_query, db_engine)
        print(f"   ✅ {len(incentives_df)} incentivos carregados")
        
        # Carregar empresas
        print("   🏢 Carregando empresas...")
        companies_query = "SELECT * FROM companies"
        companies_df = pd.read_sql(companies_query, db_engine)
        print(f"   ✅ {len(companies_df)} empresas carregadas")
        
        # Carregar matches com query corrigida
        print("   🎯 Carregando matches...")
        matches_query = """
        SELECT 
            m.incentive_id,
            i.title as incentive_title,
            i.incentive_program,
            m.company_id,
            c.company_name,
            c.cae_primary_label,
            m.keyword_score,
            m.llm_score,
            m.llm_justification
        FROM matches m
        JOIN companies c ON m.company_id = c.id
        JOIN incentives i ON m.incentive_id = i.id
        WHERE m.keyword_score IS NOT NULL 
        AND m.llm_score IS NOT NULL
        ORDER BY m.llm_score DESC
        LIMIT 100
        """
        
        try:
            matches_df = pd.read_sql(matches_query, db_engine)
            
            # Limpar dados corrompidos de forma mais robusta
            if not matches_df.empty:
                # Converter scores para numérico
                matches_df['keyword_score'] = pd.to_numeric(matches_df['keyword_score'], errors='coerce')
                matches_df['llm_score'] = pd.to_numeric(matches_df['llm_score'], errors='coerce')
                
                # Remover linhas com scores inválidos
                matches_df = matches_df.dropna(subset=['keyword_score', 'llm_score'])
                
                # Filtrar scores válidos (0-10 para LLM, 0-100 para keywords)
                matches_df = matches_df[
                    (matches_df['llm_score'] >= 0) & (matches_df['llm_score'] <= 10) &
                    (matches_df['keyword_score'] >= 0) & (matches_df['keyword_score'] <= 100)
                ]
            
            print(f"   ✅ {len(matches_df)} matches carregados (após limpeza)")
            
        except Exception as e:
            print(f"   ⚠️ Erro ao carregar matches: {e}")
            matches_df = pd.DataFrame()  # DataFrame vazio em caso de erro
            print(f"   ✅ 0 matches carregados (erro na query)")
        
        # Fechar engine
        db_engine.dispose()
        
        # Indexar dados
        print(f"\n🔄 Indexando dados...")
        start_time = time.time()
        
        # 1. Indexar incentivos
        print("   📋 Indexando incentivos...")
        kb.index_incentives(incentives_df)
        
        # 2. Indexar empresas (todas em lotes)
        print("   🏢 Indexando empresas (lotes completos)...")
        try:
            kb.index_companies(companies_df)
            print("   ✅ Empresas indexadas com sucesso")
        except Exception as e:
            print(f"   ❌ Falha na indexação de empresas: {e}")
        
        # 3. Indexar matches
        print("   🎯 Indexando matches...")
        try:
            if not matches_df.empty:
                kb.index_matches(matches_df)
                print("   ✅ Matches indexados com sucesso")
            else:
                print("   ⚠️ Nenhum match para indexar")
        except Exception as e:
            print(f"   ⚠️ Erro na indexação de matches: {e}")
        
        indexing_time = time.time() - start_time
        
        # Verificar resultado final
        try:
            final_incentives = kb.collections['incentives'].count()
            final_companies = kb.collections['companies'].count()
            final_matches = kb.collections['matches'].count()
            
            print(f"\n✅ INDEXAÇÃO CONCLUÍDA!")
            print(f"   ⏱️ Tempo: {indexing_time:.1f}s")
            print(f"   📊 Resultado:")
            print(f"      - Incentivos: {final_incentives} chunks")
            print(f"      - Empresas: {final_companies} documentos")
            print(f"      - Matches: {final_matches} documentos")
            
        except Exception as e:
            print(f"❌ Erro ao verificar resultado: {e}")
        
        return kb, chatbot
        
    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")
        return None, None

def test_rag_system(chatbot):
    """Testar sistema RAG com perguntas exemplo"""
    
    if not chatbot or not chatbot.enabled:
        print("❌ Chatbot não disponível para teste")
        return
    
    print(f"\n🧪 TESTANDO SISTEMA RAG")
    print("=" * 50)
    
    test_questions = [
        "Quais são os melhores incentivos para empresas de tecnologia?",
        "Que empresas foram matchadas para incentivos de I&D?",
        "Mostra-me incentivos do programa PT2030"
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"\n{i}. Pergunta: {question}")
        
        try:
            result = chatbot.chat(question)
            
            print(f"   ⏱️ Tempo: {result['processing_time']:.1f}s")
            print(f"   📊 Documentos: {result.get('num_docs_used', 0)}")
            print(f"   🤖 Resposta: {result['response'][:200]}...")
            
            # Delay entre testes para evitar rate limiting (AUMENTADO)
            time.sleep(12)  # Aumentado de 3s para 12s
            
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            # Delay maior em caso de erro de quota
            if "429" in str(e) or "quota" in str(e).lower():
                print("   ⏳ Aguardando 10s devido a rate limit...")
                time.sleep(10)

if __name__ == "__main__":
    # Inicializar sistema
    kb, chatbot = initialize_rag_database()
    
    if kb and chatbot:
        # Testar sistema
        test_rag_system(chatbot)
        
        print(f"\n🎉 SISTEMA RAG PRONTO!")
        print("   Execute 'streamlit run streamlit_app.py' para usar o dashboard")
    else:
        print("❌ Falha na inicialização do sistema RAG")

"""
Script para pré-computar embeddings de TODAS as empresas
Executa 1x offline, salva embeddings em arquivo numpy
Reduz matching de 3min → 5s
"""

import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os
from tqdm import tqdm
import pickle

load_dotenv('config.env')

def precompute_company_embeddings():
    """Pre-computa embeddings para todas as 250k empresas"""
    
    # Conectar ao banco (usar DATABASE_URL para evitar problemas com caracteres especiais)
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        # Fallback: construir manualmente com URL encoding
        from urllib.parse import quote_plus
        password = quote_plus(os.getenv('DB_PASSWORD', ''))
        db_url = f"postgresql://{os.getenv('DB_USER')}:{password}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    
    engine = create_engine(db_url)
    
    print("📊 Carregando empresas do banco...")
    query = """
        SELECT 
            id,
            company_name,
            cae_primary_label,
            trade_description_native
        FROM companies
        ORDER BY id
    """
    companies_df = pd.read_sql(query, engine)
    print(f"   ✓ {len(companies_df):,} empresas carregadas")
    
    # Inicializar modelo
    print("🔧 Carregando modelo de embeddings...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Preparar textos
    print("📝 Preparando textos...")
    company_texts = []
    company_ids = []
    
    for _, row in tqdm(companies_df.iterrows(), total=len(companies_df), desc="Preparando"):
        cae = str(row['cae_primary_label'])
        desc = str(row['trade_description_native'])
        
        # CAE tem mais peso (repetido 2x) + descrição
        company_text = f"{cae} {cae} {desc}" if desc and desc != 'nan' else cae
        
        if company_text and company_text.strip():
            company_texts.append(company_text)
            company_ids.append(row['id'])
    
    print(f"   ✓ {len(company_texts):,} textos preparados")
    
    # Calcular embeddings em BATCH
    print("🔄 Calculando embeddings (isso vai demorar ~10-15 min uma única vez)...")
    embeddings = model.encode(
        company_texts,
        batch_size=1024,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    )
    
    print(f"   ✓ Embeddings: shape={embeddings.shape}")
    
    # Salvar embeddings
    print("💾 Salvando embeddings...")
    output_dir = 'embeddings_cache'
    os.makedirs(output_dir, exist_ok=True)
    
    np.save(f'{output_dir}/company_embeddings.npy', embeddings)
    
    # Salvar mapeamento ID → índice
    id_to_index = {company_id: i for i, company_id in enumerate(company_ids)}
    with open(f'{output_dir}/id_to_index.pkl', 'wb') as f:
        pickle.dump(id_to_index, f)
    
    # Salvar IDs
    np.save(f'{output_dir}/company_ids.npy', np.array(company_ids))
    
    print(f"\n✅ Embeddings salvos em '{output_dir}/'")
    print(f"   - company_embeddings.npy: {embeddings.nbytes / 1e6:.1f} MB")
    print(f"   - company_ids.npy: {len(company_ids):,} IDs")
    print(f"   - id_to_index.pkl: {len(id_to_index):,} mapeamentos")
    
    print("\n🚀 Próximo passo: Modificar optimized_matching.py para usar esses embeddings")
    
    engine.dispose()

if __name__ == '__main__':
    precompute_company_embeddings()

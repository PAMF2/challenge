import pandas as pd
#!/usr/bin/env python
"""Minimal Streamlit UI with two tabs: Matching (on-demand) and Chat (RAG)."""

import os
from typing import Dict, List

import streamlit as st
from dotenv import load_dotenv

from database.matching_service import DatabaseMatchingService

load_dotenv("config.env")

DB_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_STATUS_FILTER = None if os.getenv("MATCHING_STATUS_FILTER", "all").lower() == "all" else "Active"

st.set_page_config(page_title="Incentivos PT", layout="wide")
st.markdown(
    """
    <style>
    .main .block-container {padding-top: 2rem;}
    .section-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 0.85rem;
        padding: 1.4rem 1.6rem;
        margin-bottom: 1.5rem;
    }
    .section-card h4 {
        margin-top: 0;
        margin-bottom: 0.8rem;
    }
    .card-list {
        margin: 0;
        padding-left: 1.2rem;
    }
    .chip-container {
        display: flex;
        flex-wrap: wrap;
        gap: 0.5rem;
        margin-bottom: 1rem;
    }
    .chip {
        background: linear-gradient(120deg, rgba(148, 93, 255, 0.25), rgba(46, 158, 255, 0.15));
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 999px;
        padding: 0.4rem 0.9rem;
        font-size: 0.9rem;
        color: inherit;
    }
    .chip strong {
        font-weight: 600;
    }
    .stTabs [role="tab"] {
        border-radius: 999px;
        padding: 0.35rem 1rem;
        margin-right: 0.35rem;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(120deg, rgba(148, 93, 255, 0.4), rgba(46, 158, 255, 0.35));
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("🏛️ Incentivos & Matching")
st.caption("Painel unificado para executar o matching sob demanda e conversar com o assistente especializado.")


@st.cache_resource(show_spinner=False)
def get_rag_components():
    """Inicializar (uma vez) a base RAG e o chatbot."""
    from core.rag_system import initialize_rag_system

    kb, chatbot = initialize_rag_system(DB_URL, GEMINI_API_KEY)
    return kb, chatbot


@st.cache_data(show_spinner=False)
def load_incentives(status_filter: str | None = DEFAULT_STATUS_FILTER) -> pd.DataFrame:
    """Carregar incentivos disponíveis para seleção."""
    from database.matching_service import DatabaseMatchingService

    service = DatabaseMatchingService(DB_URL)
    service.connect()
    try:
        incentives_df = service.load_incentives(status_filter=status_filter)
    finally:
        service.disconnect()
    return incentives_df


def build_incentive_options(df: pd.DataFrame) -> Dict[str, str]:
    """Criar mapping título detalhado -> incentive_project_id."""
    options: Dict[str, str] = {}
    for _, row in df.iterrows():
        incentive_id = str(row.get("incentive_project_id", ""))
        title = row.get("title", "Sem título")
        label = f"{incentive_id} · {title[:80]}" if incentive_id else title[:80]
        options[label] = incentive_id
    return options


matching_tab, chat_tab = st.tabs(["⚙️ Matching", "💬 Chat"])

with matching_tab:
    st.markdown("### ⚙️ Matching sob demanda")
    st.markdown(
        """
        <div class="section-card">
            <h4>Como funciona</h4>
            <ol class="card-list">
                <li>Escolha até <strong>5 incentivos</strong> para reprocessar.</li>
                <li>Defina se deseja <strong>reindexar</strong> o RAG ao final.</li>
                <li>Acompanhe os <strong>Top 5 matches</strong> gerados e exporte em CSV.</li>
            </ol>
        </div>
        """,
        unsafe_allow_html=True,
    )

    incentives_df = load_incentives()
    incentive_options = build_incentive_options(incentives_df)

    all_options = list(incentive_options.keys())
    selected_labels = st.multiselect(
        "Escolha até 5 incentivos",
        options=all_options,
        default=[],
        help="Use a busca para localizar rapidamente um incentivo pelo título ou ID.",
        max_selections=5,
    )
    selected_ids: List[str] = [incentive_options[label] for label in selected_labels]

    summary = st.session_state.get(
        "last_run_summary",
        {"incentives": 0, "matches": 0},
    )

    metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
    metrics_col1.metric("Incentivos disponíveis", len(incentives_df))
    metrics_col2.metric("Selecionados nesta rodada", len(selected_ids))
    metrics_col3.metric("Matches gerados na última execução", summary.get("matches", 0))

    if selected_labels:
        chips_html = "".join(
            [
                f"<span class='chip'><strong>{i+1}</strong> · {label}</span>"
                for i, label in enumerate(selected_labels)
            ]
        )
        st.markdown(
            f"<div class='chip-container'>{chips_html}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Nenhum incentivo selecionado ainda. Utilize o campo acima para começar.")

    st.divider()

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        reindex_after = st.checkbox(
            "Reindexar base RAG após o matching",
            value=False,
            help="Atualiza imediatamente o ChromaDB com os novos matches gravados no banco.",
        )
    with col2:
        limit_input = st.number_input(
            "Máx. incentivos nesta rodada",
            min_value=1,
            max_value=max(len(selected_ids), 1),
            value=min(len(selected_ids) or 1, 5),
            help="Evite processar muitos incentivos de uma vez para respeitar a cota do LLM.",
        )
    with col3:
        verbose_matching = st.checkbox(
            "Verbose",
            value=False,
            help="Exibir logs detalhados no terminal durante o matching.",
        )

    st.markdown("---")
    run_matching = st.button(
        "🚀 Executar Matching",
        type="primary",
        disabled=not selected_ids,
        use_container_width=True,
    )

    if run_matching:
        st.write("---")
        st.info(
            f"Iniciando matching para {min(len(selected_ids), int(limit_input))} incentivo(s) selecionado(s)..."
        )
        match_ids = selected_ids[: int(limit_input)]

        progress_placeholder = st.empty()
        results_container = st.container()

        with st.spinner("Carregando dados e inicializando motor..."):
            service = DatabaseMatchingService(DB_URL, gemini_api_key=GEMINI_API_KEY)
            service.connect()
            try:
                companies_df = service.load_companies()
                service.initialize_matching_engine(companies_df)
            except Exception as exc:
                service.disconnect()
                st.error(f"Erro ao inicializar motor de matching: {exc}")
                st.stop()

        matches_found = 0
        total_time = 0.0
        detailed_results = []

        try:
            for index, incentive_id in enumerate(match_ids, 1):
                incentive_row = incentives_df[
                    incentives_df['incentive_project_id'].astype(str) == incentive_id
                ]
                if incentive_row.empty:
                    progress_placeholder.warning(f"Incentivo {incentive_id} não encontrado na base.")
                    continue

                incentive_row = incentive_row.iloc[0]
                progress_placeholder.info(
                    f"[{index}/{len(match_ids)}] Processando: {incentive_id} · {incentive_row['title'][:60]}..."
                )

                with st.spinner("Executando funil de matching..."):
                    try:
                        matches_df = service.process_single_incentive(
                            incentive_row,
                            verbose=verbose_matching,
                        )
                    except Exception as exc:
                        st.error(f"Erro ao processar {incentive_id}: {exc}")
                        continue

                if matches_df is not None and not matches_df.empty:
                    matches_found += len(matches_df)
                    detailed_results.append((incentive_row, matches_df))
                else:
                    progress_placeholder.warning(
                        f"Nenhum match encontrado para {incentive_id}."
                    )

        finally:
            service.disconnect()

        progress_placeholder.empty()

        if detailed_results:
            st.success(f"Matching concluído para {len(detailed_results)} incentivo(s).")
            total_incentives = len(detailed_results)
            avg_matches = matches_found / total_incentives if total_incentives else 0
            res_col1, res_col2, res_col3 = st.columns(3)
            res_col1.metric("Incentivos processados", total_incentives)
            res_col2.metric("Matches agregados", matches_found)
            res_col3.metric("Matches médios por incentivo", f"{avg_matches:.1f}")

            for incentive_row, matches_df in detailed_results:
                display_df = matches_df.copy()

                if 'rank' not in display_df.columns:
                    display_df['rank'] = range(1, len(display_df) + 1)
                else:
                    numeric_ranks = pd.to_numeric(display_df['rank'], errors='coerce')
                    if numeric_ranks.isna().all():
                        display_df['rank'] = range(1, len(display_df) + 1)
                    else:
                        display_df['rank'] = numeric_ranks.fillna(method='ffill').fillna(method='bfill').fillna(0).astype(int)

                if 'company_name' not in display_df.columns:
                    display_df['company_name'] = 'N/A'
                else:
                    display_df['company_name'] = display_df['company_name'].fillna('N/A')

                if 'keyword_score' not in display_df.columns:
                    display_df['keyword_score'] = 0.0
                else:
                    display_df['keyword_score'] = display_df['keyword_score'].fillna(0.0)

                if 'llm_score' not in display_df.columns:
                    display_df['llm_score'] = 0.0
                else:
                    display_df['llm_score'] = display_df['llm_score'].fillna(0.0)

                if 'llm_justification' not in display_df.columns:
                    if 'justificacao' in display_df.columns:
                        display_df['llm_justification'] = display_df['justificacao'].fillna('N/A')
                    elif 'rationale' in display_df.columns:
                        display_df['llm_justification'] = display_df['rationale'].fillna('N/A')
                    else:
                        display_df['llm_justification'] = 'N/A'
                else:
                    display_df['llm_justification'] = display_df['llm_justification'].fillna('N/A')

                with results_container.expander(
                    f"🎯 {incentive_row['incentive_project_id']} · {incentive_row['title']}"
                ):
                    top5_df = display_df[[
                        'rank',
                        'company_name',
                        'keyword_score',
                        'llm_score',
                        'llm_justification'
                    ]].head(5)

                    st.dataframe(top5_df, use_container_width=True)

                    csv_data = top5_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Baixar CSV (Top 5)",
                        data=csv_data,
                        file_name=f"matches_{incentive_row['incentive_project_id']}.csv",
                        mime="text/csv",
                    )
            st.session_state["last_run_summary"] = {
                "incentives": len(detailed_results),
                "matches": matches_found,
            }
        else:
            st.error("Nenhum match foi gerado nesta rodada (verifique limites da API ou dados do incentivo).")
            st.session_state["last_run_summary"] = {
                "incentives": 0,
                "matches": 0,
            }

        if reindex_after and detailed_results:
            st.info("💡 Para reindexar a base RAG com os novos matches, execute: `python initialize_rag.py`")
            # Reindexação automática removida para simplificar o código
            # Para reindexar manualmente: python initialize_rag.py

with chat_tab:
    st.subheader("Chat")
    st.caption(
        "Converse com o assistente sobre incentivos, empresas e resultados. "
        "O RAG recupera contexto atualizado e utiliza matches recém-gerados quando disponíveis."
    )

    with st.container():
        st.markdown(
            """
            <div class="section-card">
                <h4>Dicas rápidas</h4>
                <ul class="card-list">
                    <li>Peça recomendações por setor ou dimensão (ex.: "Quais incentivos para startups de energia?").</li>
                    <li>Acompanhe follow-ups específicos (ex.: "Que requisitos a empresa X precisa cumprir?").</li>
                    <li>Combine com os matches recentes (ex.: "Explique por que a empresa Y apareceu no Top 5").</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    kb, chatbot = get_rag_components()

    if "history" not in st.session_state:
        st.session_state["history"] = []

    history: List = st.session_state["history"]

    with st.container():
        turns = len(history)
        last_docs = len(history[-1][1].get("retrieved_docs", [])) if history else 0
        chat_metrics_col1, chat_metrics_col2 = st.columns(2)
        chat_metrics_col1.metric("Mensagens na conversa", turns)
        chat_metrics_col2.metric("Fontes na última resposta", last_docs)

    if not history:
        st.info("Faça uma pergunta para começar a conversa.")

    for user_msg, result in history:
        with st.chat_message("user"):
            st.markdown(user_msg)
        with st.chat_message("assistant"):
            st.markdown(result['response'])
            docs = result.get("retrieved_docs", [])
            if docs:
                with st.expander("Ver contexto utilizado"):
                    for doc in docs:
                        metadata = doc.get("metadata", {})
                        st.markdown(
                            f"- **Fonte:** `{metadata.get('doc_type', 'desconhecido')}` | "
                            f"**Similaridade:** {doc.get('similarity', 0):.2f} | "
                            f"**Título:** {metadata.get('title', metadata.get('company_name', 'N/A'))}"
                        )
                        st.write(doc.get("content", ""))
                        st.markdown("---")

    user_input = st.chat_input("Digite sua mensagem")

    if user_input:
        with st.spinner("Buscando contexto e gerando resposta..."):
            result = chatbot.chat(
                user_input,
                history=[(msg, res['response']) for msg, res in history]
            )
        st.session_state["history"].append((user_input, result))
        st.rerun()

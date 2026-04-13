# rag_upload_app.py
# ---------------------------------------------------------------------------
# Streamlit UI for uploading, managing, and testing RAG policy documents.
# This is a SEPARATE interface from the main new_app.py.
# Run: streamlit run rag_upload_app.py
# ---------------------------------------------------------------------------

import streamlit as st
from pathlib import Path
from datetime import datetime

from rag_engine import (
    ingest_from_bytes,
    retrieve_as_text,
    retrieve,
    list_documents,
    delete_document,
    delete_document_by_name,
    get_stats,
    reset_rag,
    SUPPORTED_EXTENSIONS,
    UPLOAD_DIR,
)

st.set_page_config(
    page_title="RAG Policy Document Manager",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .upload-header { font-size: 2rem; color: #1E3A8A; font-weight: 700; margin-bottom: 0.5rem; }
    .section-header { font-size: 1.3rem; color: #3B82F6; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.5rem; border-bottom: 2px solid #E2E8F0; padding-bottom: 0.3rem; }
    .success-box { background: #D1FAE5; border-left: 4px solid #065F46; padding: 12px 16px; border-radius: 4px; margin: 8px 0; }
    .error-box { background: #FEE2E2; border-left: 4px solid #991B1B; padding: 12px 16px; border-radius: 4px; margin: 8px 0; }
    .info-box { background: #DBEAFE; border-left: 4px solid #1E40AF; padding: 12px 16px; border-radius: 4px; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="upload-header">📄 RAG Policy Document Manager</div>', unsafe_allow_html=True)
st.caption(
    "Upload and manage banking policy documents (loan policies, credit score guidelines, "
    "compliance rules, etc.) that will be used by the loan creation agents for policy-aware decisions."
)

# Sidebar
with st.sidebar:
    st.header("📊 Database Stats")
    stats = get_stats()
    st.metric("Total Documents", stats["total_documents"])
    st.metric("Total Chunks", stats["total_chunks"])

    if stats["categories"]:
        st.markdown("**Categories:**")
        for cat in stats["categories"]:
            st.markdown(f"- `{cat}`")

    st.divider()
    st.subheader("⚙️ Actions")
    if st.button("🗑️ Reset Entire Database", type="secondary", use_container_width=True):
        if st.session_state.get("confirm_reset"):
            result = reset_rag()
            st.session_state.confirm_reset = False
            st.success("Database reset complete!")
            st.rerun()
        else:
            st.session_state.confirm_reset = True
            st.warning("Click again to confirm reset — this will delete ALL documents!")

    st.divider()
    st.caption(
        f"**Storage:** `{stats['storage_dir']}`\n\n"
        f"**Uploads:** `{stats['upload_dir']}`\n\n"
        f"**Supported formats:** {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )

# Tabs
tab1, tab2, tab3 = st.tabs(["📤 Upload Documents", "📚 Document Library", "🔍 Test Search"])

# Tab 1: Upload
with tab1:
    st.markdown('<div class="section-header">📤 Upload Policy Documents</div>', unsafe_allow_html=True)
    st.markdown("""
    Upload banking policy documents that the loan creation agents will reference
    when evaluating loan applications. Supported: **PDF**, **DOCX**, **TXT / Markdown**.
    """)

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded_files = st.file_uploader(
            "Select policy documents", type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
            accept_multiple_files=True,
        )
    with col2:
        category = st.selectbox("Document Category",
            options=["general", "loan_policy", "credit_score", "compliance",
                     "risk_assessment", "eligibility", "regulatory"], index=0)
        tags_input = st.text_input("Tags (comma-separated)",
            placeholder="e.g., FICO, DTI, mortgage, personal-loan")

    if uploaded_files and st.button("🚀 Ingest Documents", type="primary", use_container_width=True):
        tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
        progress_bar = st.progress(0, text="Processing...")
        results = []
        for i, file in enumerate(uploaded_files):
            file_bytes = file.read()
            progress_bar.progress(i / len(uploaded_files), text=f"Ingesting: {file.name}...")
            result = ingest_from_bytes(file_bytes=file_bytes, file_name=file.name,
                                       category=category, tags=tags)
            results.append(result)
        progress_bar.progress(1.0, text="Complete!")

        st.markdown("---")
        success_count = sum(1 for r in results if r["status"].startswith("success"))
        skipped_count = sum(1 for r in results if r["status"].startswith("skipped"))
        error_count = sum(1 for r in results if r["status"].startswith("error"))

        for result in results:
            if result["status"].startswith("success"):
                st.markdown(f'<div class="success-box">✅ <strong>{result["file_name"]}</strong> — {result["total_chunks"]} chunks ingested</div>', unsafe_allow_html=True)
            elif result["status"].startswith("skipped"):
                st.markdown(f'<div class="info-box">⏭️ <strong>{result["file_name"]}</strong> — {result["status"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="error-box">❌ <strong>{result["file_name"]}</strong> — {result["status"]}</div>', unsafe_allow_html=True)

        st.markdown(f"**Summary:** {success_count} ingested, {skipped_count} skipped, {error_count} errors")
        st.rerun()

# Tab 2: Document Library
with tab2:
    st.markdown('<div class="section-header">📚 Document Library</div>', unsafe_allow_html=True)
    docs = list_documents()
    if not docs:
        st.info("No documents in the RAG database yet. Go to the Upload tab to add policy documents.")
    else:
        for doc in docs:
            col1, col2, col3 = st.columns([4, 2, 1])
            with col1:
                st.markdown(f"**📄 {doc['file_name']}**")
                st.caption(f"Category: `{doc['category']}` | Chunks: {doc['total_chunks']} | "
                           f"Ingested: {doc.get('ingested_at', 'N/A')[:19] if doc.get('ingested_at') else 'N/A'}")
                if doc.get("tags"):
                    tag_list = [t.strip() for t in doc["tags"].split(",") if t.strip()]
                    st.markdown(f"Tags: {' '.join(f'`{t}`' for t in tag_list)}")
            with col2:
                st.metric("Chunks", doc["total_chunks"])
            with col3:
                if st.button("🗑️ Delete", key=f"del_{doc['file_hash']}", type="secondary"):
                    delete_document(doc["file_hash"])
                    st.success(f"Deleted: {doc['file_name']}")
                    st.rerun()
            st.divider()

# Tab 3: Test Search
with tab3:
    st.markdown('<div class="section-header">🔍 Test Policy Search</div>', unsafe_allow_html=True)
    st.markdown("Test the RAG retrieval to verify that your policy documents are indexed correctly.")

    col1, col2 = st.columns([3, 1])
    with col1:
        test_query = st.text_input("Search Query",
            value="What is the minimum FICO score required for loan approval?")
    with col2:
        test_category = st.selectbox("Category Filter",
            options=["All Categories", "loan_policy", "credit_score", "compliance",
                     "risk_assessment", "eligibility", "regulatory", "general"], index=0)

    test_n_results = st.slider("Number of Results", min_value=1, max_value=10, value=5, step=1)

    if st.button("🔎 Search", type="primary", use_container_width=True):
        if not test_query.strip():
            st.warning("Please enter a search query.")
        else:
            with st.spinner("Searching policy documents..."):
                category_filter = None if test_category == "All Categories" else test_category
                formatted_text = retrieve_as_text(query=test_query, n_results=test_n_results,
                                                 category=category_filter)
            st.markdown("---")
            if "No relevant policy documents found" in formatted_text:
                st.warning(formatted_text)
            else:
                st.text_area("Formatted Results (as agents would see them)", value=formatted_text,
                             height=500, disabled=True)
                individual_results = retrieve(query=test_query, n_results=test_n_results,
                                              category=category_filter)
                if individual_results:
                    st.markdown("---")
                    st.markdown('<div class="section-header">📊 Result Details</div>', unsafe_allow_html=True)
                    for i, result in enumerate(individual_results, 1):
                        with st.expander(f"Result {i}: {result['file_name']} (Relevance: {result['relevance_score']:.1%})", expanded=(i <= 2)):
                            st.markdown(f"**Source:** {result['file_name']}")
                            st.markdown(f"**Category:** {result['category']}")
                            st.markdown(f"**Relevance Score:** {result['relevance_score']:.1%}")
                            st.markdown("---")
                            st.markdown(result["content"])
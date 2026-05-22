"""Streamlit paper-trading dashboard.

Phase 9: production-feel UI on top of the locked Phase 7 strategy. Heavy
computations (signal panels, optimizer path, regime masks) are cached
once per session via @st.cache_data so navigation between tabs is instant.

Run:
    uv run streamlit run scripts/dashboard.py
"""

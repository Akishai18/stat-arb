"""Launch the streamlit dashboard.

    uv run streamlit run scripts/dashboard.py

Streamlit expects a script to execute its UI code on import; this file is
the entrypoint Streamlit watches for reloads. All actual UI logic lives
in `statarb.dashboard.app`.
"""

from statarb.dashboard.app import main

main()

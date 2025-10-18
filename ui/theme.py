# ui/theme.py
import streamlit as st

def load_styles():
    try:
        with open("styles.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

def badge(text, kind="ok"):
    # kind: ok | warn | danger
    return f'<span class="badge {kind}">{text}</span>'

def card(title, body_md):
    st.markdown(f"""
    <div class="card">
        <h4>{title}</h4>
        <div>{body_md}</div>
    </div>
    """, unsafe_allow_html=True)

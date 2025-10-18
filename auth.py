# auth.py
import streamlit as st

USUARIOS = {
    "Mateo": "Almacen123",
    "Juliana": "abcd",
    "admin": "admin"
}

ADMINS = {"Mateo", "Juliana"}

def login():
    if "usuario" not in st.session_state:
        st.session_state.usuario = None
        st.session_state.is_admin = False

    if st.session_state.usuario:
        return True

    st.markdown("""
        <style>
        .login-outer-container { display:flex; flex-direction:column; justify-content:center; align-items:center; height:35vh; }
        .main-title { font-size:2.0rem; color:#fff; background:#00cc66; padding:.6rem 1.2rem; border-radius:12px; margin-bottom:1rem; }
        .login-box { background:#1e1e1e; padding:1.2rem 1.6rem; border-radius:12px; max-width:380px; width:100%; }
        .login-title { background:#00cc66; padding:.5rem; color:white; text-align:center; border-radius:8px; font-size:1.1rem; margin-bottom:1rem; font-weight:bold;}
        </style>
        <div class="login-outer-container">
            <div class="main-title">🗂️ INVENTARIO TICS </div>
            <div class="login-box">
                <div class="login-title">🔐 Inicio de sesión</div>
    """, unsafe_allow_html=True)

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Iniciar sesión", type="primary", use_container_width=True):
        if usuario in USUARIOS and USUARIOS[usuario] == password:
            st.session_state.usuario = usuario
            st.session_state.is_admin = usuario in ADMINS
            st.success(f"Sesión iniciada como {usuario}")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")

    st.markdown("</div></div>", unsafe_allow_html=True)
    return False

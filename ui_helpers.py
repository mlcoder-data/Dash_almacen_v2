# ui_helpers.py
import streamlit as st
from patterns import Result

def ui_result(r: Result):
    if getattr(r, "ok", False):
        if r.msg:
            st.success(r.msg)
    else:
        st.error(getattr(r, "error", "Ocurrió un error."))

# main.py

import streamlit as st
import pandas as pd
from datetime import datetime
import altair as alt

# --- Cargar estilos globales (después de importar streamlit) ---
def load_styles():
    try:
        with open("styles.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        # Si aún no copiaste styles.css no rompe la app
        pass

load_styles()

from streamlit_option_menu import option_menu
from auth import login  # maneja sesión y roles en st.session_state
from database import (
    ensure_db,
    registrar_evento, obtener_historial, eliminar_registro,
    obtener_inventario, agregar_equipo, llave_activa_por_salon
)

# ---------------------- Configuración base ----------------------
st.set_page_config(page_title="Control de Llaves e Inventario", layout="wide")
ensure_db()

# ---------------------- Utilidades ----------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def procesar_fechas(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if "fecha_hora" in df.columns:
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], errors="coerce")
        df["fecha"] = df["fecha_hora"].dt.date
        df["hora"] = df["fecha_hora"].dt.strftime("%H:%M")
        df["día_semana"] = df["fecha_hora"].dt.day_name()
    return df

def filtros_comunes(df: pd.DataFrame, key_prefix="flt") -> pd.DataFrame:
    """Aplica filtros típicos a un DataFrame del historial."""
    if df is None or df.empty:
        return df

    df = procesar_fechas(df.copy())
    profesores = ["Todos"] + sorted(df["nombre"].dropna().unique().tolist())
    salones = ["Todos"] + sorted(df["salon"].dropna().unique().tolist())
    areas = ["Todos"] + sorted(df["area"].dropna().unique().tolist())
    dias = ["Todos"] + sorted(df["día_semana"].dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    with c1:
        f_prof = st.selectbox("Profesor", profesores, key=f"{key_prefix}_prof")
    with c2:
        f_salon = st.selectbox("Salón", salones, key=f"{key_prefix}_salon")
    with c3:
        f_area = st.selectbox("Área", areas, key=f"{key_prefix}_area")

    c4, c5 = st.columns(2)
    with c4:
        f_dia = st.selectbox("Día de la semana", dias, key=f"{key_prefix}_dia")
    with c5:
        f_rango = st.date_input("Rango de fechas", [], key=f"{key_prefix}_rango")

    if f_prof != "Todos":
        df = df[df["nombre"] == f_prof]
    if f_salon != "Todos":
        df = df[df["salon"] == f_salon]
    if f_area != "Todos":
        df = df[df["area"] == f_area]
    if f_dia != "Todos":
        df = df[df["día_semana"] == f_dia]

    if isinstance(f_rango, list) and len(f_rango) == 2:
        ini, fin = f_rango
        df = df[(df["fecha"] >= ini) & (df["fecha"] <= fin)]

    return df


# ----------- Bloques visuales reutilizables -----------

def badge(text, kind="ok"):
    """
    Retorna un span con estilos de badge.
    kind puede ser: ok | warn | danger
    """
    return f'<span class="badge {kind}">{text}</span>'

def card(title, body_md):
    """
    Crea una tarjeta estilizada con título y contenido en Markdown.
    Usa el CSS global 'card' que agregaste.
    """
    st.markdown(f"""
    <div class="card">
        <h4>{title}</h4>
        <div>{body_md}</div>
    </div>
    """, unsafe_allow_html=True)


#------------------------- Ajuste de menú ----------------------

with st.sidebar:
    st.markdown("### 💬 Menú\n**Principal**")
    st.divider()
    menu = option_menu(
        menu_title=None,
        options=["Registrar llave", "Historial", "Estadísticas", "Inventario por salón", "Llaves activas"],
        icons=["pencil-square", "clock-history", "bar-chart", "diagram-3", "key"],
        default_index=0,
        styles={
            "container": {"padding": "0"},
            "icon": {"font-size": "16px"},
            "nav-link": {"font-weight": "600", "border-radius": "12px"},
            "nav-link-selected": {"background-color": "#ff5a5f"},
        },
    )

#---------------------- fin menú ----------------------



# ---------------------- Autenticación ----------------------
if not login():
    st.stop()

usuario = st.session_state.usuario
is_admin = bool(st.session_state.get("is_admin", False))

# ---------------------- Sidebar ----------------------
with st.sidebar:
    st.markdown(f"**Usuario:** {usuario}")
    if is_admin:
        st.caption("Rol: Administrador")
    else:
        st.caption("Rol: Operador")

    menu = st.radio(
        "Navegación",
        ["Dashboard", "Registrar llave", "Llaves activas", "Historial", "Inventario"],
        index=0
    )

    if st.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()

# ---------------------- Páginas ----------------------
if menu == "Dashboard":
    st.header("📊 Dashboard")
    hist = obtener_historial()
    inv = obtener_inventario()

    # KPIs simples
    total_registros = 0 if hist is None else len(hist)
    total_inventario = 0 if inv is None else len(inv)

    # llaves activas por última acción "Entregada"
    activas = 0
    if hist is not None and not hist.empty:
        h2 = procesar_fechas(hist)
        ultimas = h2.sort_values("fecha_hora").groupby("salon").tail(1)
        activas = int((ultimas["accion"] == "Entregada").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros (llaves)", total_registros)
    c2.metric("Llaves activas", activas)
    c3.metric("Activos en inventario", total_inventario)

    st.divider()
    st.subheader("Últimos movimientos (llaves)")
    if hist is None or hist.empty:
        st.info("Aún no hay movimientos.")
    else:
        df = procesar_fechas(hist).sort_values("fecha_hora", ascending=False).head(20)
        st.dataframe(df[["fecha_hora", "nombre", "area", "salon", "accion"]], use_container_width=True)

elif menu == "Registrar llave":
    st.header("📝 Registrar movimiento de llave")

    with st.form("form_llave", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nombre = st.text_input("Profesor/Instructor *")
            area = st.text_input("Área/Programa *")
        with c2:
            salon = st.text_input("Código de salón *", placeholder="Ej: C3-204")
            accion = st.selectbox("Acción *", ["Entregada", "Devuelta"])

        enviado = st.form_submit_button("Registrar", type="primary")
        if enviado:
            if not nombre or not area or not salon or not accion:
                st.error("Completa los campos obligatorios (*)")
            else:
                if accion == "Entregada" and llave_activa_por_salon(salon):
                    st.error(f"La llave del salón {salon} ya está prestada. Primero debe devolverse.")
                else:
                    registrar_evento(nombre, area, salon, accion, now_str())
                    st.success(f"Registro exitoso: llave {accion.lower()} para el salón {salon}")
                    st.rerun()
    """""
elif menu == "Llaves activas":
    st.header("🔒 Llaves actualmente entregadas")
    data = obtener_historial()
    if data is None or data.empty:
        st.success("✅ No hay llaves prestadas actualmente.")
    else:
        df = procesar_fechas(data)
        # Última acción por salón
        ult = df.sort_values("fecha_hora").groupby("salon").tail(1)
        activas = ult[ult["accion"] == "Entregada"].copy()

        if activas.empty:
            st.success("✅ No hay llaves prestadas actualmente.")
        else:
            # Filtros rápidos
            colf1, colf2, colf3 = st.columns(3)
            with colf1:
                f_prof = st.selectbox("Profesor", ["Todos"] + sorted(activas["nombre"].unique().tolist()))
            with colf2:
                f_area = st.selectbox("Área", ["Todos"] + sorted(activas["area"].unique().tolist()))
            with colf3:
                f_salon = st.selectbox("Salón", ["Todos"] + sorted(activas["salon"].unique().tolist()))

            if f_prof != "Todos":
                activas = activas[activas["nombre"] == f_prof]
            if f_area != "Todos":
                activas = activas[activas["area"] == f_area]
            if f_salon != "Todos":
                activas = activas[activas["salon"] == f_salon]

            # Pintar tarjetas con botón devolver
            for idx, row in activas.iterrows():
                cA, cB = st.columns([5, 1])
                with cA:
                    st.markdown(
                        f"**{row['salon']}** — otorgada a **{row['nombre']}** ({row['area']})  \n"
                        f"🕒 {row['fecha_hora'].strftime('%Y-%m-%d %H:%M')}"
                    )
                with cB:
                    if st.button("Devolver", key=f"dev_{idx}"):
                        registrar_evento(row["nombre"], row["area"], row["salon"], "Devuelta", now_str())
                        st.success(f"Llave de {row['salon']} devuelta.")
                        st.rerun()
    """

elif menu == "Llaves activas":
    st.header("🔒 Llaves actualmente entregadas")
    data = obtener_historial()
    if data is None or data.empty:
        st.success("✅ No hay llaves prestadas actualmente.")
    else:
        df = procesar_fechas(data)
        # Última acción por salón
        ult = df.sort_values("fecha_hora").groupby("salon").tail(1)
        activas = ult[ult["accion"] == "Entregada"].copy()

        if activas.empty:
            st.success("✅ No hay llaves prestadas actualmente.")
        else:
            st.markdown("### 📋 Lista de llaves entregadas")
            for _, row in activas.iterrows():
                estado = badge("Entregada", "warn")
                card(
                    f"Salón {row['salon']} — {estado}",
                    f"👤 **{row['nombre']}** · 🏫 {row['area']}  \n🕒 {row['fecha_hora'].strftime('%Y-%m-%d %H:%M')}"
                )
                if st.button(f"Devolver {row['salon']}", key=f"dev_{row['id']}"):
                    registrar_evento(row["nombre"], row["area"], row["salon"], "Devuelta", now_str())
                    st.success(f"Llave de {row['salon']} devuelta correctamente.")
                    st.rerun()

elif menu == "Historial":
    st.header("📜 Historial de movimientos")
    data = obtener_historial()
    if data is None or data.empty:
        st.info("No hay registros aún.")
    else:
        df = filtros_comunes(data, key_prefix="hist")
        st.dataframe(
            df[["id", "fecha_hora", "nombre", "area", "salon", "accion"]],
            use_container_width=True, hide_index=True
        )

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Descargar CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="historial_llaves.csv",
                mime="text/csv"
            )
        with col2:
            if is_admin:
                del_id = st.number_input("Eliminar por ID (solo admin)", min_value=0, step=1)
                if st.button("Eliminar registro", type="secondary"):
                    if del_id > 0 and del_id in df["id"].values:
                        eliminar_registro(int(del_id))
                        st.success(f"Registro {int(del_id)} eliminado.")
                        st.rerun()
                    else:
                        st.warning("ID no encontrado en la vista filtrada.")

elif menu == "Inventario":
    st.header("🧰 Inventario de equipos (simple)")
    tab1, tab2 = st.tabs(["Agregar equipo", "Ver inventario"])

    with tab1:
        with st.form("form_inv", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                nombre = st.text_input("Nombre del equipo *", placeholder="Osciloscopio, Multímetro…")
                tipo = st.text_input("Tipo/Categoría *", placeholder="Osciloscopio / PC / Herramienta")
            with c2:
                estado = st.selectbox("Estado *", ["Disponible", "En uso", "Dañado", "Extraviado"])
                salon = st.text_input("Salón", placeholder="C3-204")
            with c3:
                responsable = st.text_input("Responsable", placeholder="(opcional)")
                fecha_registro = now_str()

            if st.form_submit_button("Guardar equipo", type="primary"):
                if not nombre or not tipo or not estado:
                    st.error("Completa los campos obligatorios (*)")
                else:
                    agregar_equipo(nombre, tipo, estado, salon or "", responsable or "", fecha_registro)
                    st.success("Equipo agregado al inventario.")
                    st.rerun()

    with tab2:
        inv = obtener_inventario()
        if inv is None or inv.empty:
            st.info("No hay equipos registrados.")
        else:
            df = inv.copy()
            c1, c2, c3 = st.columns(3)
            with c1:
                f_tipo = st.selectbox("Filtrar por tipo", ["Todos"] + sorted(df["tipo"].dropna().unique().tolist()))
            with c2:
                f_estado = st.selectbox("Filtrar por estado", ["Todos"] + sorted(df["estado"].dropna().unique().tolist()))
            with c3:
                f_salon = st.selectbox("Filtrar por salón", ["Todos"] + sorted(df["salon"].dropna().unique().tolist()))

            if f_tipo != "Todos":
                df = df[df["tipo"] == f_tipo]
            if f_estado != "Todos":
                df = df[df["estado"] == f_estado]
            if f_salon != "Todos":
                df = df[df["salon"] == f_salon]

            st.dataframe(
                df[["id", "nombre", "tipo", "estado", "salon", "responsable", "fecha_registro"]],
                use_container_width=True, hide_index=True
            )
            st.download_button(
                "Exportar inventario (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="inventario.csv",
                mime="text/csv"
            )

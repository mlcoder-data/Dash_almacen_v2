# database.py
import sqlite3
import pandas as pd
from pathlib import Path

from database_utils import txn
from validators import validar_equipo, norm_salon, norm_placa
from patterns import OK, ERR, Result
from errors import ValidationError, ConflictError, NotFoundError, IntegrityError
from validators import normalizar_salon_label, titlecase_nombre

# ---- RUTA ÚNICA Y CONEXIÓN ----
RUTA_BD = str(Path(__file__).with_name("llaves.db"))

def obtener_conexion():
    """Crea y devuelve una conexión SQLite con configuración estándar."""
    conn = sqlite3.connect(RUTA_BD, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

# ---- ESQUEMA BASE (llaves + inventario) ----
ESQUEMA_BASE = """
CREATE TABLE IF NOT EXISTS llaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,          -- profesor/instructor
    area TEXT,
    salon TEXT,
    accion TEXT,          -- Entregada | Devuelta
    fecha_hora TEXT       -- ISO 'YYYY-MM-DD HH:MM:SS'
);
CREATE INDEX IF NOT EXISTS idx_llaves_salon_fecha ON llaves(salon, fecha_hora);
CREATE INDEX IF NOT EXISTS idx_llaves_accion ON llaves(accion);

CREATE TABLE IF NOT EXISTS inventario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    tipo TEXT,
    estado TEXT,          -- Disponible | En uso | Dañado | Extraviado
    salon TEXT,
    responsable TEXT,
    fecha_registro TEXT
);
CREATE INDEX IF NOT EXISTS idx_inventario_salon ON inventario(salon);
"""

# ---- ESQUEMA EXTRA (rooms + índices útiles) ----
ESQUEMA_INVENTARIO = """
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE NOT NULL,
    nombre TEXT,
    edificio TEXT,
    piso TEXT,
    observaciones TEXT
);
CREATE INDEX IF NOT EXISTS idx_rooms_codigo ON rooms(codigo);

CREATE INDEX IF NOT EXISTS idx_inv_estado ON inventario(estado);
CREATE INDEX IF NOT EXISTS idx_inv_tipo ON inventario(tipo);
CREATE INDEX IF NOT EXISTS idx_inv_salon ON inventario(salon);
"""

def ensure_db():
    """Crea tablas base y deja inventario listo (placa + movimientos)."""
    conn = obtener_conexion()
    conn.executescript(ESQUEMA_BASE)
    conn.commit(); conn.close()

    # Extras
    asegurar_esquema_inventario()
    asegurar_campo_placa()
    asegurar_esquema_movimientos()


def asegurar_esquema_inventario():
    """Crea tablas/índices adicionales para inventario/rooms si no existen."""
    conn = obtener_conexion()
    conn.executescript(ESQUEMA_INVENTARIO)
    conn.commit()
    conn.close()


# -------------------------------------------------------------------
#  FUNCIONES: LLAVES
# -------------------------------------------------------------------
def registrar_evento(nombre, area, salon, accion, fecha_hora):
    conn = obtener_conexion()
    conn.execute(
        "INSERT INTO llaves (nombre, area, salon, accion, fecha_hora) VALUES (?, ?, ?, ?, ?)",
        (nombre, area, salon, accion, fecha_hora),
    )
    conn.commit()
    conn.close()

def obtener_historial():
    conn = obtener_conexion()
    df = pd.read_sql_query("SELECT * FROM llaves ORDER BY datetime(fecha_hora) DESC", conn)
    conn.close()
    return df

def eliminar_registro(registro_id: int):
    conn = obtener_conexion()
    conn.execute("DELETE FROM llaves WHERE id = ?", (registro_id,))
    conn.commit()
    conn.close()

def llave_activa_por_salon(salon: str) -> bool:
    """True si la última acción para ese salón es 'Entregada'."""
    conn = obtener_conexion()
    row = conn.execute(
        "SELECT accion FROM llaves WHERE salon=? ORDER BY datetime(fecha_hora) DESC LIMIT 1",
        (salon,)
    ).fetchone()
    conn.close()
    return bool(row and row["accion"] == "Entregada")


# -------------------------------------------------------------------
#  FUNCIONES: ROOMS (SALONES)
# -------------------------------------------------------------------
def registrar_salon(codigo, nombre=None, edificio=None, piso=None, observaciones=None):
    """Inserta o actualiza un salón (evita duplicados por código)."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return None
    conn = obtener_conexion()
    cur = conn.cursor()

    cur.execute("SELECT id FROM rooms WHERE codigo=?", (codigo,))
    existente = cur.fetchone()

    if existente:
        cur.execute(
            """UPDATE rooms 
               SET nombre=COALESCE(?,nombre),
                   edificio=COALESCE(?,edificio),
                   piso=COALESCE(?,piso),
                   observaciones=COALESCE(?,observaciones)
               WHERE codigo=?""",
            (nombre, edificio, piso, observaciones, codigo),
        )
        conn.commit()
        conn.close()
        return existente["id"]

    cur.execute(
        "INSERT INTO rooms (codigo, nombre, edificio, piso, observaciones) VALUES (?,?,?,?,?)",
        (codigo, nombre, edificio, piso, observaciones),
    )
    conn.commit()
    nuevo_id = cur.lastrowid
    conn.close()
    return nuevo_id

def obtener_salones():
    conn = obtener_conexion()
    df = pd.read_sql_query("SELECT * FROM rooms ORDER BY codigo", conn)
    conn.close()
    return df


# -------------------------------------------------------------------
#  FUNCIONES: INVENTARIO (CRUD + MASIVO)
# -------------------------------------------------------------------
def obtener_inventario():
    conn = obtener_conexion()
    df = pd.read_sql_query(
        "SELECT * FROM inventario ORDER BY datetime(fecha_registro) DESC, id DESC", conn
    )
    conn.close()
    return df


def agregar_equipo(nombre, tipo, estado, salon, responsable, fecha_registro, placa=None):
    conn = obtener_conexion()
    conn.execute(
        """INSERT INTO inventario (nombre, tipo, estado, salon, responsable, fecha_registro, placa)
           VALUES (?,?,?,?,?,?,?)""",
        (nombre, tipo, estado, salon, responsable, fecha_registro, placa),
    )
    conn.commit(); conn.close()


def actualizar_equipo(id_equipo: int, **campos):
    if not campos:
        return
    # validar placa única si viene en la actualización
    if "placa" in campos and campos["placa"]:
        conn = obtener_conexion()
        row = conn.execute(
            "SELECT id FROM inventario WHERE placa=? AND id<>?",
            (campos["placa"], int(id_equipo))
        ).fetchone()
        conn.close()
        if row:
            raise ValueError(f"La placa {campos['placa']} ya existe en otro equipo.")

    sets = ", ".join([f"{k}=?" for k in campos.keys()])
    valores = list(campos.values()) + [id_equipo]
    conn = obtener_conexion()
    conn.execute(f"UPDATE inventario SET {sets} WHERE id=?", valores)
    conn.commit(); conn.close()


def eliminar_equipo(id_equipo: int):
    conn = obtener_conexion()
    conn.execute("DELETE FROM inventario WHERE id=?", (id_equipo,))
    conn.commit()
    conn.close()

def insertar_inventario_masivo(df: pd.DataFrame):
    """Inserta múltiples registros validados en el inventario."""
    if df is None or df.empty:
        return 0

    # Normaliza columna placa (opcional)
    if "placa" not in df.columns:
        df["placa"] = None
    else:
        df["placa"] = df["placa"].fillna("").astype(str).str.strip().replace({"": None})

    # Validación de duplicados en el propio archivo (ignora vacíos)
    dup_archivo = df["placa"].dropna()
    if dup_archivo.duplicated().any():
        dups = sorted(dup_archivo[dup_archivo.duplicated()].unique().tolist())
        raise ValueError(f"Placas duplicadas en el archivo: {dups}")

    # Validación contra BD
    conn = obtener_conexion()
    cur = conn.cursor()
    conflictivas = []
    for p in df["placa"].dropna().unique().tolist():
        r = cur.execute("SELECT id FROM inventario WHERE placa=?", (p,)).fetchone()
        if r:
            conflictivas.append(p)
    conn.close()
    if conflictivas:
        raise ValueError(f"Placas ya existentes en BD: {sorted(conflictivas)}")

    # Inserción
    conn = obtener_conexion()
    datos = df[["nombre", "tipo", "estado", "salon", "responsable", "fecha_registro", "placa"]].values.tolist()
    conn.executemany(
        "INSERT INTO inventario (nombre, tipo, estado, salon, responsable, fecha_registro, placa) "
        "VALUES (?,?,?,?,?,?,?)",
        datos,
    )
    conn.commit()
    cant = conn.total_changes
    conn.close()
    return cant


# --- MIGRACIÓN: asegurar columna PLACA única (opcional) ---
def asegurar_campo_placa():
    """
    Agrega la columna 'placa' a inventario si no existe y crea índice único
    (solo cuando placa no es nula ni vacía).
    """
    conn = obtener_conexion()
    cur = conn.cursor()

    # ¿Existe la columna?
    cur.execute("PRAGMA table_info(inventario)")
    cols = [r["name"] for r in cur.fetchall()]
    if "placa" not in cols:
        cur.execute("ALTER TABLE inventario ADD COLUMN placa TEXT")
        conn.commit()

    # Índice único parcial (evita duplicados solo cuando hay valor)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_inv_placa_unique
        ON inventario(placa)
        WHERE placa IS NOT NULL AND placa <> ''
    """)
    conn.commit()
    conn.close()


def existe_placa(placa: str) -> bool:
    """Devuelve True si la placa ya existe en inventario (no vacía)."""
    if not placa:
        return False
    conn = obtener_conexion()
    row = conn.execute(
        "SELECT 1 FROM inventario WHERE placa=? AND placa<>'' LIMIT 1", (placa,)
    ).fetchone()
    conn.close()
    return bool(row)

# ========= ESQUEMA: movimientos de equipos =========
ESQUEMA_MOVIMIENTOS = """
CREATE TABLE IF NOT EXISTS inventario_movs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventario_id INTEGER NOT NULL,
    placa TEXT,
    salon_origen TEXT,
    salon_destino TEXT NOT NULL,
    motivo TEXT,              -- traslado, préstamo, mantenimiento, etc.
    responsable TEXT,         -- quién solicitó/ejecutó
    fecha_hora TEXT NOT NULL, -- ISO 'YYYY-MM-DD HH:MM:SS'
    notas TEXT,
    FOREIGN KEY(inventario_id) REFERENCES inventario(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_movs_inv ON inventario_movs(inventario_id);
CREATE INDEX IF NOT EXISTS idx_movs_placa ON inventario_movs(placa);
CREATE INDEX IF NOT EXISTS idx_movs_fecha ON inventario_movs(fecha_hora);
"""

def asegurar_esquema_movimientos():
    conn = obtener_conexion()
    conn.executescript(ESQUEMA_MOVIMIENTOS)
    conn.commit()
    conn.close()

# ---- Helpers movimientos ----
def registrar_movimiento_equipo(inventario_id:int, placa:str, salon_origen:str, salon_destino:str,
                                motivo:str, responsable:str, fecha_hora:str, notas:str=None):
    conn = obtener_conexion()
    conn.execute(
        """INSERT INTO inventario_movs
           (inventario_id, placa, salon_origen, salon_destino, motivo, responsable, fecha_hora, notas)
           VALUES (?,?,?,?,?,?,?,?)""",
        (int(inventario_id),
         (placa or None),
         (salon_origen or None),
         (salon_destino or None),
         (motivo or None),
         (responsable or None),
         fecha_hora,
         (notas or None))
    )
    conn.commit(); conn.close()

def mover_equipo(inventario_id:int, nuevo_salon:str, motivo:str, responsable:str,
                 fecha_hora:str, notas:str=None):
    conn = obtener_conexion()
    cur = conn.cursor()

    with txn(conn):
        # Datos actuales
        cur.execute("SELECT id, salon, placa FROM inventario WHERE id=?", (int(inventario_id),))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Equipo id={inventario_id} no existe")

        salon_origen = (row["salon"] or "").strip().upper()
        placa_actual = (row["placa"] or None)
        nuevo_salon_up = (nuevo_salon or "").strip().upper()

        # Update inventario
        cur.execute("UPDATE inventario SET salon=? WHERE id=?", (nuevo_salon_up, int(inventario_id)))

        # Log movimiento
        cur.execute(
            """INSERT INTO inventario_movs
               (inventario_id, placa, salon_origen, salon_destino, motivo, responsable, fecha_hora, notas)
               VALUES (?,?,?,?,?,?,?,?)""",
            (int(inventario_id), placa_actual, salon_origen or None, nuevo_salon_up or None,
             (motivo or None), (responsable or None), fecha_hora, (notas or None))
        )

def obtener_movimientos(fecha_ini:str=None, fecha_fin:str=None, placa:str=None,
                        salon_origen:str=None, salon_destino:str=None, responsable:str=None):
    """
    Devuelve DataFrame de movimientos con filtros opcionales (fechas en 'YYYY-MM-DD').
    """
    base = """SELECT id, inventario_id, placa, salon_origen, salon_destino, motivo,
                     responsable, fecha_hora, notas
              FROM inventario_movs WHERE 1=1"""
    params = []
    if fecha_ini:
        base += " AND date(fecha_hora) >= date(?)"; params.append(fecha_ini)
    if fecha_fin:
        base += " AND date(fecha_hora) <= date(?)"; params.append(fecha_fin)
    if placa:
        base += " AND placa = ?"; params.append(placa)
    if salon_origen:
        base += " AND salon_origen = ?"; params.append(salon_origen.upper())
    if salon_destino:
        base += " AND salon_destino = ?"; params.append(salon_destino.upper())
    if responsable:
        base += " AND responsable LIKE ?"; params.append(f"%{responsable}%")

    base += " ORDER BY datetime(fecha_hora) DESC, id DESC"
    conn = obtener_conexion()
    df = pd.read_sql_query(base, conn, params=params)
    conn.close()
    return df

def movimientos_por_placa(placa:str):
    return obtener_movimientos(placa=(placa or "").strip().upper())

# --- SAFE WRAPPERS (usan validators + Result + txn) ---
def agregar_equipo_safe(nombre, tipo, estado, salon, responsable, fecha_registro, placa=None) -> Result:
    try:
        nombre, tipo, estado = validar_equipo(nombre, tipo, estado)
        salon = norm_salon(salon)
        placa = norm_placa(placa)

        if placa and existe_placa(placa):
            return ERR(f"La placa {placa} ya existe.")

        conn = obtener_conexion()
        with txn(conn):
            if salon != "BODEGA":
                conn.execute("INSERT OR IGNORE INTO rooms(codigo) VALUES (?)", (salon,))
            conn.execute(
                """INSERT INTO inventario (nombre, tipo, estado, salon, responsable, fecha_registro, placa)
                   VALUES (?,?,?,?,?,?,?)""",
                (nombre, tipo, estado, salon, (responsable or ""), fecha_registro, placa),
            )
        return OK(True)
    except ValidationError as e:
        return ERR(str(e))
    except IntegrityError as e:
        return ERR("Violación de unicidad (placa).")
    except Exception as e:
        return ERR(f"Error al agregar equipo: {e}")

def actualizar_equipo_safe(id_equipo:int, **campos) -> Result:
    try:
        if "salon" in campos and campos["salon"]:
            campos["salon"] = norm_salon(campos["salon"])
        if "placa" in campos:
            p = norm_placa(campos["placa"])
            campos["placa"] = p
            if p:
                conn = obtener_conexion()
                row = conn.execute(
                    "SELECT id FROM inventario WHERE placa=? AND id<>?", (p, int(id_equipo))
                ).fetchone()
                conn.close()
                if row:
                    return ERR(f"La placa {p} ya existe en otro equipo.")

        actualizar_equipo(id_equipo, **campos)
        return OK(True)
    except Exception as e:
        return ERR(f"Error al actualizar: {e}")

def eliminar_equipo_safe(id_equipo:int) -> Result:
    try:
        eliminar_equipo(id_equipo)
        return OK(True)
    except Exception as e:
        return ERR(f"Error al eliminar: {e}")

def insertar_inventario_masivo_safe(df: pd.DataFrame) -> Result:
    try:
        # normaliza columnas clave
        for c in ["nombre","tipo","estado","salon","responsable","fecha_registro"]:
            if c not in df.columns:
                return ERR(f"Falta columna obligatoria: {c}")

        # limpieza básica
        for c in df.columns:
            if df[c].dtype == object:
                df[c] = df[c].astype(str).str.strip()
        df["tipo"]   = df["tipo"].str.title()
        df["estado"] = df["estado"].str.title()
        df["salon"]  = df["salon"].str.upper().fillna("")
        if "placa" in df.columns:
            df["placa"] = df["placa"].fillna("").str.upper().replace({"": None})
        else:
            df["placa"] = None

        cant = insertar_inventario_masivo(df)
        return OK(cant)
    except Exception as e:
        return ERR(f"Error en carga masiva: {e}")

def mover_equipo_safe(inventario_id:int, nuevo_salon:str, motivo:str, responsable:str,
                      fecha_hora:str, notas:str=None) -> Result:
    try:
        nuevo_salon = norm_salon(nuevo_salon)
        mover_equipo(inventario_id, nuevo_salon, motivo, responsable, fecha_hora, notas)
        return OK(True)
    except Exception as e:
        return ERR(f"Error al mover equipo: {e}")

from patterns import Result, OK, ERR
from validators import validar_equipo, norm_salon, norm_placa

def agregar_equipo_safe(nombre, tipo, estado, salon, responsable, fecha_registro, placa=None) -> Result:
    # Validaciones de dominio
    err = validar_equipo(nombre, tipo, estado, salon, fecha_registro)
    if err: return ERR(err)

    salon_n = norm_salon(salon)
    placa_n = norm_placa(placa)

    # Unicidad de placa (si viene)
    if placa_n and existe_placa(placa_n):
        return ERR(f"La placa {placa_n} ya existe.")

    try:
        conn = obtener_conexion()
        with txn(conn):
            # asegurar salón si no existe
            registrar_salon(salon_n)
            # insertar
            conn.execute(
                """INSERT INTO inventario (nombre, tipo, estado, salon, responsable, fecha_registro, placa)
                   VALUES (?,?,?,?,?,?,?)""",
                (nombre.strip(), tipo.strip().title(), estado.strip(), salon_n,
                 (responsable or "").strip(), fecha_registro, placa_n),
            )
        conn.close()
        return OK()
    except Exception as e:
        try: conn.close()
        except: pass
        return ERR(f"Error guardando equipo: {e}")

def mover_equipo_safe(inventario_id:int, salon_destino:str, motivo:str, responsable:str, fecha_hora:str, notas:str|None=None) -> Result:
    try:
        conn = obtener_conexion()
        with txn(conn):
            # leer actual
            row = conn.execute("SELECT id, salon, placa FROM inventario WHERE id=?", (int(inventario_id),)).fetchone()
            if not row: return ERR(f"Equipo id={inventario_id} no existe")

            origen = (row["salon"] or "").strip().upper()
            destino = norm_salon(salon_destino)

            registrar_salon(destino)

            conn.execute("UPDATE inventario SET salon=? WHERE id=?", (destino, int(inventario_id)))
            conn.execute(
                """INSERT INTO inventario_movs (inventario_id, placa, salon_origen, salon_destino, motivo, responsable, fecha_hora, notas)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (int(inventario_id), (row["placa"] or None), origen or None, destino or None,
                 (motivo or None), (responsable or None), fecha_hora, (notas or None))
            )
        conn.close()
        return OK()
    except Exception as e:
        try: conn.close()
        except: pass
        return ERR(f"Error moviendo equipo: {e}")

# database.py
from validators import normalizar_salon_label, titlecase_nombre

def _get_db_version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]

def _set_db_version(conn, v: int) -> None:
    conn.execute(f"PRAGMA user_version = {v}")

def _migration_1_normalize_data(conn):
    """Normaliza salones y nombres ya existentes."""
    cur = conn.cursor()

    # llaves: normalizar salón
    for _id, salon in cur.execute("SELECT id, salon FROM llaves").fetchall():
        new = normalizar_salon_label(salon or "")
        if new and new != (salon or ""):
            cur.execute("UPDATE llaves SET salon=? WHERE id=?", (new, _id))

    # llaves: normalizar nombre
    for _id, nombre in cur.execute("SELECT id, nombre FROM llaves").fetchall():
        new = titlecase_nombre(nombre or "")
        if new and new != (nombre or ""):
            cur.execute("UPDATE llaves SET nombre=? WHERE id=?", (new, _id))

    # inventario: normalizar salón
    for _id, salon in cur.execute("SELECT id, salon FROM inventario").fetchall():
        new = normalizar_salon_label(salon or "")
        if new and new != (salon or ""):
            cur.execute("UPDATE inventario SET salon=? WHERE id=?", (new, _id))

def run_startup_migrations():
    """
    Ejecuta migraciones pendientes UNA sola vez, controlado por user_version.
    - v0 -> v1: normalización de salones y nombres existentes
    """
    conn = obtener_conexion()
    try:
        ver = _get_db_version(conn)
        if ver < 1:
            _migration_1_normalize_data(conn)
            _set_db_version(conn, 1)
            conn.commit()
    finally:
        conn.close()

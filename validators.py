# validators.py
from patterns import OK, ERR, Result
# --- Normalizador de salones (etiqueta de interfaz) ---
import re

CATEGORIAS_VALIDAS = [
    "Computador","Portátil","Cargador","Osciloscopio","Multímetro",
    "Fuente","Router","Switch","Herramienta","Televisor","Proyector","Otro"
]
ESTADOS_VALIDOS = ["Disponible","En uso","Dañado","Extraviado"]

def norm(s: str | None) -> str:
    return (s or "").strip()

def norm_upper(s: str | None) -> str:
    return (s or "").strip().upper()

def norm_salon(s: str | None) -> str:
    v = norm_upper(s)
    return v if v else "BODEGA"

def norm_placa(s: str | None):
    v = norm_upper(s)
    return v or None

def validar_equipo(nombre: str, tipo: str, estado: str, salon: str, placa: str | None = None) -> Result:
    nombre = norm(nombre)
    tipo   = (tipo or "").strip().title()
    estado = norm(estado)
    salon  = norm_salon(salon)
    placa  = norm_placa(placa)

    if not nombre:
        return ERR("El nombre del equipo es obligatorio.")
    if tipo not in CATEGORIAS_VALIDAS:
        return ERR(f"Tipo inválido. Usa uno de: {', '.join(CATEGORIAS_VALIDAS)}")
    if estado not in ESTADOS_VALIDOS:
        return ERR(f"Estado inválido. Usa uno de: {', '.join(ESTADOS_VALIDOS)}")

    return OK(value={"nombre": nombre, "tipo": tipo, "estado": estado, "salon": salon, "placa": placa})

# validators.py
import re

# ---------------------------
# Helpers de texto
# ---------------------------
def _normalize_spaces(s: str) -> str:
    """Quita espacios extra y normaliza a un único espacio."""
    return re.sub(r"\s+", " ", (s or "").strip())

def titlecase_nombre(s: str) -> str:
    """
    Pone mayúscula inicial en cada palabra, respetando conectores comunes.
    Ej: 'ana maría de la cruz' -> 'Ana María de la Cruz'
    """
    s = _normalize_spaces(s)
    if not s:
        return s
    conectores = {"de", "del", "la", "las", "los", "y", "e", "da", "do"}
    partes = s.lower().split(" ")
    out = []
    for i, p in enumerate(partes):
        if p in conectores and i != 0:
            out.append(p)
        else:
            out.append(p[:1].upper() + p[1:])
    return " ".join(out)

# ---------------------------
# Validación de nombre
# ---------------------------
# Letras con tildes, ñ, apóstrofes simples, guiones y espacios. SIN números.
_NOMBRE_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’ -]+$")

def validar_nombre_instructor(nombre: str):
    """
    Devuelve (ok, msg). Acepta solo letras (con acentos), espacios, guiones y apóstrofes.
    Rechaza números u otros símbolos.
    """
    nombre = _normalize_spaces(nombre)
    if not nombre:
        return False, "El nombre es obligatorio."
    if not _NOMBRE_RE.match(nombre):
        return False, "El nombre solo puede contener letras, espacios, guiones y apóstrofes (sin números)."
    # al menos 2 caracteres alfabéticos “reales”
    if len(re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", nombre)) < 2:
        return False, "El nombre es demasiado corto."
    return True, ""

# ---------------------------
# Normalización de salones
# ---------------------------
def normalizar_salon_label(raw: str) -> str:
    """
    Normaliza distintas variantes al formato estándar:
      - 'Sala N' para números y códigos (7, SALA 7, salon 7, 316-F, 303F, etc.)
      - 'BODEGA' para bodega
    Reglas:
      • 'bodega', 'almacen', 'depósito' -> 'BODEGA'
      • token como '316F' -> '316-F' (inserta guion si hay letra al final)
      • siempre 'Sala <token>' con token en mayúsculas
    """
    s = _normalize_spaces(raw).lower()
    if not s:
        return ""

    # Bodega
    if s in {"bodega", "bodegas", "almacen", "almacén", "deposito", "depósito"}:
        return "BODEGA"

    # Quita prefijos 'sala', 'salón/salon'
    s = re.sub(r"^(sala|salon|salón)\s+", "", s, flags=re.IGNORECASE)

    token = s.upper()

    # 316F -> 316-F
    m = re.match(r"^(\d+)\s*([A-Z])$", token)
    if m:
        token = f"{m.group(1)}-{m.group(2)}"

    # 316-F -> 316-F (deja tal cual)
    # 303F-2 o extras: no tocamos, solo normalizamos espacios
    token = token.replace("  ", " ").strip()

    # si quedó solo número o alfanumérico/hífen, prefijamos Sala
    if token and token != "BODEGA":
        return f"Sala {token}"

    return token

def _normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def normalizar_salon_label(texto: str) -> str:
    t = _normalize_spaces(texto)
    if not t:
        return ""
    if t.lower() in {"bodega", "la bodega"}:
        return "BODEGA"

    # extrae patrón típico de sala: 7, 316, 303-F, 7A, 3-204, 316F, etc.
    # si no encuentra, usa todo el texto como core
    m = re.search(r"([A-Z]?\s*\d+(?:\s*-\s*\d+)?(?:\s*[A-Z])?(?:\s*-\s*[A-Z])?)", t, re.I)
    core = m.group(1) if m else t
    core = re.sub(r"\s+", "", core).upper()    #  "316 F" -> "316F", "303 - F" -> "303-F"
    core = core.replace("SALON", "").replace("SALA", "")
    core = core.strip("- ")

    return f"Sala {core}" if core else "Sala"

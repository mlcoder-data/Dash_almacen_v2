# services/inventario.py
from patterns import OK, ERR, Result
from validators import validar_equipo, norm_salon, norm_placa
from database import (
    agregar_equipo, existe_placa, registrar_salon
)

def agregar_equipo_safe(
    nombre: str, tipo: str, estado: str, salon: str,
    responsable: str, fecha_registro: str, placa: str | None = None
) -> Result:
    try:
        v = validar_equipo(nombre, tipo, estado, salon, placa)
        if not v.ok:
            return v
        data = v.value
        # placa única
        if data.get("placa") and existe_placa(data["placa"]):
            return ERR(f"La placa {data['placa']} ya existe en el inventario.")

        salon_n = norm_salon(data["salon"])
        if salon_n != "BODEGA":
            registrar_salon(salon_n)

        agregar_equipo(
            data["nombre"], data["tipo"], data["estado"], salon_n,
            (responsable or "").strip(), fecha_registro, data.get("placa")
        )
        return OK(msg="Equipo agregado correctamente.")
    except Exception as e:
        return ERR(str(e))

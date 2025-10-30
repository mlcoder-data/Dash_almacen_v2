# services/movimientos.py
from patterns import OK, ERR, Result
from validators import norm_salon
from database import mover_equipo, registrar_salon

def mover_equipo_safe(
    inventario_id: int, target: str, motivo: str,
    responsable: str, fecha_hora: str, notas: str | None = None
) -> Result:
    try:
        target_n = norm_salon(target)
        if not target_n:
            return ERR("Debes indicar el salón destino.")
        registrar_salon(target_n)  # asegura que exista
        mover_equipo(int(inventario_id), target_n, motivo, responsable or "N/A", fecha_hora, notas)
        return OK(msg=f"Equipo {inventario_id} movido a {target_n}.")
    except Exception as e:
        return ERR(str(e))

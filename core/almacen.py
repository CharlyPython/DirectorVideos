import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from core.modelos import Fase, Guion, Plan

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proyectos(
  id TEXT PRIMARY KEY, idea TEXT, titulo TEXT, fase TEXT, pausa TEXT, creado TEXT);
CREATE TABLE IF NOT EXISTS costes(
  pid TEXT, agente TEXT, concepto TEXT, usd REAL, ts TEXT);
CREATE TABLE IF NOT EXISTS logs(
  pid TEXT, agente TEXT, mensaje TEXT, ts TEXT);
"""
SUBCARPETAS = {"imagen": ("imagenes", ".png"), "clip": ("clips", ".mp4"), "audio": ("audio", ".mp3")}


class Almacen:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.raiz / "director.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(ESQUEMA)

    # --- archivos
    def ruta(self, pid: str) -> Path:
        return self.raiz / pid

    def archivo(self, pid: str, clave: str, escena_id: str) -> Path:
        carpeta, ext = SUBCARPETAS[clave]
        return self.ruta(pid) / carpeta / f"{escena_id}{ext}"

    def _escribir(self, destino: Path, texto: str) -> None:
        tmp = destino.with_suffix(destino.suffix + ".tmp")
        tmp.write_text(texto, encoding="utf-8")
        tmp.replace(destino)

    def guardar_json(self, pid: str, nombre: str, datos: dict) -> None:
        self._escribir(self.ruta(pid) / nombre, json.dumps(datos, ensure_ascii=False, indent=2))

    def cargar_json(self, pid: str, nombre: str) -> dict | None:
        p = self.ruta(pid) / nombre
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # --- proyecto
    def crear_proyecto(self, plan: Plan) -> str:
        pid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        for carpeta, _ in SUBCARPETAS.values():
            (self.ruta(pid) / carpeta).mkdir(parents=True, exist_ok=True)
        self.guardar_plan(pid, plan)
        self.db.execute("INSERT INTO proyectos VALUES(?,?,?,?,?,?)",
                        (pid, plan.idea, "", Fase.GUION.value, None, datetime.now().isoformat()))
        self.db.commit()
        return pid

    def guardar_plan(self, pid: str, plan: Plan) -> None:
        self._escribir(self.ruta(pid) / "plan.json", plan.model_dump_json(indent=2))

    def cargar_plan(self, pid: str) -> Plan:
        return Plan.model_validate_json((self.ruta(pid) / "plan.json").read_text(encoding="utf-8"))

    def tiene_guion(self, pid: str) -> bool:
        return (self.ruta(pid) / "guion.json").exists()

    def guardar_guion(self, pid: str, guion: Guion) -> None:
        self._escribir(self.ruta(pid) / "guion.json", guion.model_dump_json(indent=2))
        self.db.execute("UPDATE proyectos SET titulo=? WHERE id=?", (guion.titulo, pid))
        self.db.commit()

    def cargar_guion(self, pid: str) -> Guion:
        return Guion.model_validate_json((self.ruta(pid) / "guion.json").read_text(encoding="utf-8"))

    # --- estado
    def _campo(self, pid: str, campo: str):
        fila = self.db.execute(f"SELECT {campo} FROM proyectos WHERE id=?", (pid,)).fetchone()
        if fila is None:
            raise KeyError(pid)
        return fila[0]

    def fase(self, pid: str) -> Fase:
        return Fase(self._campo(pid, "fase"))

    def set_fase(self, pid: str, fase: Fase) -> None:
        self.db.execute("UPDATE proyectos SET fase=? WHERE id=?", (fase.value, pid))
        self.db.commit()

    def pausar(self, pid: str, motivo: str) -> None:
        self.db.execute("UPDATE proyectos SET pausa=? WHERE id=?", (motivo, pid))
        self.db.commit()

    def quitar_pausa(self, pid: str) -> None:
        self.db.execute("UPDATE proyectos SET pausa=NULL WHERE id=?", (pid,))
        self.db.commit()

    def pausa(self, pid: str) -> str | None:
        return self._campo(pid, "pausa")

    def listar(self) -> list[dict]:
        filas = self.db.execute(
            "SELECT p.*, COALESCE((SELECT SUM(usd) FROM costes c WHERE c.pid=p.id),0) AS coste "
            "FROM proyectos p ORDER BY creado DESC").fetchall()
        return [dict(f) for f in filas]

    # --- costes
    def registrar_coste(self, pid: str, agente: str, concepto: str, usd: float) -> None:
        self.db.execute("INSERT INTO costes VALUES(?,?,?,?,?)",
                        (pid, agente, concepto, float(usd), datetime.now().isoformat()))
        self.db.commit()

    def coste_total(self, pid: str) -> float:
        return self.db.execute("SELECT COALESCE(SUM(usd),0) FROM costes WHERE pid=?", (pid,)).fetchone()[0]

    def costes_por_agente(self, pid: str) -> dict[str, float]:
        filas = self.db.execute("SELECT agente, SUM(usd) FROM costes WHERE pid=? GROUP BY agente", (pid,))
        return {a: round(u, 6) for a, u in filas}

    def coste_mes(self, anio: int, mes: int) -> float:
        prefijo = f"{anio:04d}-{mes:02d}"
        return self.db.execute("SELECT COALESCE(SUM(usd),0) FROM costes WHERE ts LIKE ?",
                               (prefijo + "%",)).fetchone()[0]

    # --- logs
    def log(self, pid: str, agente: str, mensaje: str) -> None:
        self.db.execute("INSERT INTO logs VALUES(?,?,?,?)", (pid, agente, mensaje, datetime.now().isoformat()))
        self.db.commit()

    def logs(self, pid: str, limite: int = 200) -> list[dict]:
        filas = self.db.execute("SELECT agente, mensaje, ts FROM logs WHERE pid=? ORDER BY ts DESC LIMIT ?",
                                (pid, limite)).fetchall()
        return [dict(f) for f in filas]

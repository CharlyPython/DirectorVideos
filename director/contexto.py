from core.almacen import Almacen
from core.modelos import Plan
from director.eventos import Bus
from proveedores.base import Proveedores


class PresupuestoAgotado(Exception):
    pass


class Contexto:
    def __init__(self, almacen: Almacen, proveedores: Proveedores, pid: str, bus: Bus, concurrencia: int = 6):
        self.almacen, self.proveedores, self.pid, self.bus = almacen, proveedores, pid, bus
        self.concurrencia = concurrencia
        self._reservado = 0.0

    @property
    def plan(self) -> Plan:
        return self.almacen.cargar_plan(self.pid)

    def emitir(self, agente: str, mensaje: str, **extra) -> None:
        self.almacen.log(self.pid, agente, mensaje)
        self.bus.emitir(self.pid, {"agente": agente, "mensaje": mensaje, **extra})

    def reservar(self, usd: float) -> None:
        tope = self.plan.presupuesto_max
        gastado = self.almacen.coste_total(self.pid)
        if gastado + self._reservado + usd > tope + 1e-9:
            raise PresupuestoAgotado(f"Presupuesto agotado: gastado {gastado:.2f} $ de {tope:.2f} $")
        self._reservado += usd

    def liberar(self, usd: float) -> None:
        self._reservado = max(0.0, self._reservado - usd)

    def cobrar(self, agente: str, concepto: str, usd: float) -> None:
        if usd:
            self.almacen.registrar_coste(self.pid, agente, concepto, usd)

from pydantic import BaseModel


class Machine(BaseModel):
    machine_id: str
    name: str
    type: str
    zone: str
    x: int
    y: int
    manufacturer: str | None = None
    model: str | None = None
    install_year: int | None = None
    criticality: str | None = None
    downtime_cost_per_minute: int | None = None


class MachinesResponse(BaseModel):
    machines: list[Machine]

from pydantic import BaseModel
from typing import List, Optional


class MedicoEntry(BaseModel):
    """Um médico extraído do print do comando EMS."""
    id: int
    nome: str
    suspeito: bool = False
    motivo_suspeita: Optional[str] = None


class OCRResponse(BaseModel):
    total_detectado: int
    total_suspeitos: int = 0
    medicos: List[MedicoEntry]
    aviso: Optional[str] = None  # linhas que não bateram com o padrão ID: Nome (essas sim, descartadas)


class ErrorResponse(BaseModel):
    erro: str

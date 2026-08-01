from pydantic import BaseModel
from typing import List, Optional


class MedicoEntry(BaseModel):
    """Um médico extraído do print do comando EMS."""
    id: int
    nome: str


class OCRResponse(BaseModel):
    total_detectado: int
    medicos: List[MedicoEntry]
    aviso: Optional[str] = None  # ex: linhas que não bateram com o padrão ID: Nome


class ErrorResponse(BaseModel):
    erro: str

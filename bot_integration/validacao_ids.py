"""
Módulo pra COLAR dentro do cmsvalley-bot: valida e tenta corrigir as
entradas devolvidas pela API de OCR, cruzando com os membros reais do
Discord — em vez de simplesmente descartar o que a API marcou como
"suspeito" (`suspeito: true` no JSON de /ocr/ems).

A API NUNCA decide se um ID é "errado de verdade" — ela só sinaliza o que
foge do intervalo esperado. Quem resolve é o bot, porque só o bot tem
acesso à lista real de membros (Whitelist + cargos) pra confirmar.

Estratégia de validação, na ordem:
  1. ID lido bate direto com um membro conhecido -> confirmado.
  2. ID lido bate com um membro depois de corrigir 1 dígito confundível
     pela fonte do HUD (ex: 710515 -> 110515, porque "7" e "1" se
     parecem muito nessa fonte) -> corrigido por dígito.
  3. Não bate por ID de jeito nenhum -> tenta achar por NOME (fuzzy match)
     entre os membros conhecidos, e usa o ID real do membro encontrado.
  4. Não bate de nenhuma forma -> não encontrado. Nesse caso é o mesmo
     cenário que já está mapeado no sistema de plantão médico: o médico
     provavelmente é de outro hospital (ex: Hospital Norte), não do Sul.

Uso dentro do cog que já faz a chamada de verificação:

    from services.ems_ocr_client import enviar_print_ems
    from services.validacao_ids import validar_medicos, MembroConhecido

    resultado = await enviar_print_ems(print_ems)

    # você monta essa lista a partir do guild.members reais (WL + cargos
    # de médico aprovado do HP Sul Valley — ajuste pra sua lógica real)
    membros = construir_membros_conhecidos(guild)

    validados = validar_medicos(resultado["medicos"], membros)

    for v in validados:
        if v.status == "confirmado":
            ...
        elif v.status == "corrigido":
            # mostra pro Doutor: "710515 -> 110515 (Josh Scott)" antes de aceitar
            ...
        elif v.status == "nao_encontrado":
            # avisa: "Josh Scott (710515) não está no servidor — pode ser do Hospital Norte"
            ...
"""

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Dict, List, Optional


@dataclass
class MembroConhecido:
    """Um médico real do Hospital Sul, montado a partir do Discord.

    O apelido no servidor segue o formato "Nome | idFivem" (mesmo padrão
    usado na Whitelist) — é de lá que normalmente se extrai o id_fivem.
    """
    id_fivem: int
    nome: str
    discord_id: int


@dataclass
class MedicoValidado:
    id_lido: int
    nome_lido: str
    status: str  # "confirmado" | "corrigido" | "nao_encontrado"
    id_corrigido: Optional[int] = None
    membro: Optional[MembroConhecido] = None
    motivo: Optional[str] = None


# Pares de dígitos visualmente parecidos nessa fonte de HUD de jogo — usados
# pra gerar tentativas de correção quando um ID não bate com nenhum membro
# conhecido. Ajuste essa tabela se perceber outras confusões recorrentes.
_DIGITOS_CONFUNDIVEIS: Dict[str, List[str]] = {
    "0": ["8"],
    "8": ["0", "3"],
    "1": ["7"],
    "7": ["1"],
    "5": ["6"],
    "6": ["5"],
    "2": ["7"],
}

_PADRAO_APELIDO_ID = re.compile(r"\|\s*(\d{1,7})\s*$")


def extrair_id_do_apelido(apelido: str) -> Optional[int]:
    """Extrai o id_fivem de um apelido no formato 'Nome | idFivem'."""
    match = _PADRAO_APELIDO_ID.search(apelido or "")
    return int(match.group(1)) if match else None


def _candidatos_por_digito(id_str: str) -> List[str]:
    """Troca UM dígito por vez pelo(s) parecido(s) — ex: '710515' -> '110515'."""
    candidatos = []
    for i, digito in enumerate(id_str):
        for alternativa in _DIGITOS_CONFUNDIVEIS.get(digito, []):
            candidatos.append(id_str[:i] + alternativa + id_str[i + 1:])
    return candidatos


def _candidatos_por_corte(id_str: str) -> List[str]:
    """Remove o primeiro ou o último dígito — cobre o caso de um dígito extra grudado pelo OCR."""
    if len(id_str) <= 1:
        return []
    return [id_str[1:], id_str[:-1]]


def _buscar_por_nome(nome_lido: str, membros: List[MembroConhecido]) -> Optional[MembroConhecido]:
    nomes = [m.nome for m in membros]
    proximos = get_close_matches(nome_lido, nomes, n=1, cutoff=0.75)
    if not proximos:
        return None
    nome_encontrado = proximos[0]
    return next((m for m in membros if m.nome == nome_encontrado), None)


def validar_medico(id_lido: int, nome_lido: str, membros: List[MembroConhecido]) -> MedicoValidado:
    por_id = {m.id_fivem: m for m in membros}

    # 1. bate direto
    if id_lido in por_id:
        return MedicoValidado(id_lido, nome_lido, status="confirmado", membro=por_id[id_lido])

    # 2. tenta corrigir por confusão de dígito (ex: 710515 -> 110515)
    id_str = str(id_lido)
    for candidato_str in _candidatos_por_digito(id_str) + _candidatos_por_corte(id_str):
        if not candidato_str.isdigit():
            continue
        candidato_id = int(candidato_str)
        if candidato_id in por_id:
            return MedicoValidado(
                id_lido, nome_lido,
                status="corrigido",
                id_corrigido=candidato_id,
                membro=por_id[candidato_id],
                motivo=f"ID lido como {id_lido}, corrigido pra {candidato_id} (confusão de dígito)",
            )

    # 3. não bateu por número nenhum — tenta pelo nome
    membro_por_nome = _buscar_por_nome(nome_lido, membros)
    if membro_por_nome:
        return MedicoValidado(
            id_lido, nome_lido,
            status="corrigido",
            id_corrigido=membro_por_nome.id_fivem,
            membro=membro_por_nome,
            motivo=f"ID não batia, encontrado pelo nome ('{nome_lido}' ~ '{membro_por_nome.nome}')",
        )

    # 4. não encontrado de nenhuma forma
    return MedicoValidado(
        id_lido, nome_lido,
        status="nao_encontrado",
        motivo="Não encontrado entre os membros do Hospital Sul — pode ser médico de outro hospital (ex: Norte).",
    )


def validar_medicos(medicos_api: List[dict], membros: List[MembroConhecido]) -> List[MedicoValidado]:
    """Valida a lista inteira devolvida pela API (`resultado["medicos"]`)."""
    return [validar_medico(m["id"], m["nome"], membros) for m in medicos_api]

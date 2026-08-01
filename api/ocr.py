import os
import re
import tempfile
from typing import List, Tuple

from gradio_client import Client, handle_file

# ---------------------------------------------------------------------------
# Motor de OCR: chama o Space público da comunidade que roda o DeepSeek-OCR,
# em vez de rodar qualquer modelo aqui dentro. Decisão consciente: é grátis
# e a qualidade se mostrou melhor que o EasyOCR nessa fonte específica do
# HUD (ver testes feitos), mas isso significa que essa API agora DEPENDE de
# um serviço de terceiro, hospedado por uma pessoa da comunidade, sem SLA
# nenhum. Se ele cair ou mudar a API, o /ocr/ems para de funcionar até
# alguém trocar SPACE_ID ou reverter pro EasyOCR (ver git history / README).
# ---------------------------------------------------------------------------
SPACE_ID = os.getenv("DEEPSEEK_OCR_SPACE", "khang119966/DeepSeek-OCR-DEMO")
MODEL_SIZE = os.getenv("DEEPSEEK_OCR_MODEL_SIZE", "Tiny")  # Tiny, Base, Small, Medium, Large

# Usa .search (não .match) e não ancora no fim da linha — casa mesmo quando
# o modelo devolve algum caractere estranho antes/depois do ID:Nome.
_LINE_PATTERN = re.compile(r"(\d{1,7})\s*[:.\-]\s*(.+)")

# Intervalo esperado de IDs FiveM válidos nesse servidor — nunca existe ID 0,
# negativo, ou acima de 200000. A API NÃO descarta quem cai fora disso — ela
# só marca a entrada como "suspeita" e manda pro bot mesmo assim. Quem decide
# o que fazer com isso é o bot — ver validacao_ids.py em bot_integration/.
ID_MINIMO = 1
ID_MAXIMO = 200_000


class OcrIndisponivelError(Exception):
    """O Space de terceiro que faz o OCR está fora do ar ou não respondeu."""


_client: "Client | None" = None


def _get_client() -> Client:
    """Conecta no Space só na primeira chamada (não trava o startup da API
    se o Space estiver temporariamente fora do ar quando o serviço sobe)."""
    global _client
    if _client is None:
        try:
            _client = Client(SPACE_ID)
        except Exception as exc:
            raise OcrIndisponivelError(
                f"Não foi possível conectar no Space de OCR ({SPACE_ID}): {exc}"
            ) from exc
    return _client


def _rodar_modelo(caminho_imagem: str) -> str:
    """Manda a imagem pro Space e devolve o texto reconhecido bruto."""
    client = _get_client()
    try:
        texto, _imagem_com_boxes = client.predict(
            image=handle_file(caminho_imagem),
            model_size=MODEL_SIZE,
            task_type="📝 Free OCR",
            ref_text="",
            api_name="/process_ocr_task",
        )
    except Exception as exc:
        raise OcrIndisponivelError(
            f"O Space de OCR ({SPACE_ID}) não respondeu: {exc}"
        ) from exc
    return texto or ""


def _parse_lines(texto: str) -> Tuple[List[dict], List[str]]:
    """Separa linhas em: reconhecidas (válidas ou suspeitas) e sem padrão 'ID: Nome'.

    Uma linha só é descartada de verdade quando o regex não acha NENHUM
    'número : nome' nela. Se o padrão bate mas o número foge do intervalo
    esperado, a entrada é marcada como "suspeito" e enviada mesmo assim —
    quem decide se corrige, descarta ou pede confirmação manual é o bot.
    """
    medicos = []
    sem_padrao = []
    for linha in texto.splitlines():
        linha = linha.strip().lstrip("#").strip()  # tira lixo tipo "# Atenção" de markdown
        if not linha:
            continue

        match = _LINE_PATTERN.search(linha)
        if not match:
            sem_padrao.append(linha)
            continue

        id_str, nome = match.groups()
        id_num = int(id_str)
        suspeito = not (ID_MINIMO <= id_num <= ID_MAXIMO)

        entrada = {"id": id_num, "nome": nome.strip(), "suspeito": suspeito}
        if suspeito:
            entrada["motivo_suspeita"] = (
                f"ID fora do intervalo esperado ({ID_MINIMO}-{ID_MAXIMO})"
            )
        medicos.append(entrada)

    return medicos, sem_padrao


def extrair_medicos_do_print(image_bytes: bytes) -> dict:
    """Recebe os bytes da imagem do print do EMS e devolve a lista ID/Nome.

    Mesma assinatura e mesmo formato de retorno de sempre — main.py,
    models.py, o site e o bot_integration não precisam mudar nada.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        texto = _rodar_modelo(tmp_path)
    finally:
        os.remove(tmp_path)

    medicos, sem_padrao = _parse_lines(texto)
    total_suspeitos = sum(1 for m in medicos if m["suspeito"])

    aviso = None
    if sem_padrao:
        aviso = f"{len(sem_padrao)} linha(s) não bateram com o padrão 'ID: Nome' e foram ignoradas."

    return {
        "total_detectado": len(medicos),
        "total_suspeitos": total_suspeitos,
        "medicos": medicos,
        "aviso": aviso,
    }

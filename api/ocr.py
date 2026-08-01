import os
import re
import tempfile
from typing import List, Tuple

import requests
from gradio_client import Client, handle_file

# ---------------------------------------------------------------------------
# Motor de OCR: chama um serviço externo em vez de rodar qualquer modelo
# aqui dentro. O provedor é escolhido por env var (OCR_PROVIDER):
#   - "ocrspace"  (default) -> OCR.space, serviço dedicado com API key própria
#                              e cota mensal documentada — o mais estável dos
#                              três, não depende de Space de terceiro
#   - "deepseek"            -> Space da comunidade khang119966/DeepSeek-OCR-DEMO
#   - "unlimited"           -> Space oficial baidu/Unlimited-OCR
#
# Pra trocar em produção: só muda a env var OCR_PROVIDER no Render, sem
# editar nem reimplantar código.
# ---------------------------------------------------------------------------
PROVIDER = os.getenv("OCR_PROVIDER", "ocrspace").strip().lower()

OCRSPACE_ENDPOINT = os.getenv("OCRSPACE_ENDPOINT", "https://api.ocr.space/parse/image")
OCRSPACE_API_KEY = os.getenv("OCRSPACE_API_KEY", "")  # NUNCA commitar valor real aqui
OCRSPACE_LANGUAGE = os.getenv("OCRSPACE_LANGUAGE", "por")
OCRSPACE_ENGINE = os.getenv("OCRSPACE_ENGINE", "2")

DEEPSEEK_SPACE = os.getenv("DEEPSEEK_OCR_SPACE", "khang119966/DeepSeek-OCR-DEMO")
DEEPSEEK_MODEL_SIZE = os.getenv("DEEPSEEK_OCR_MODEL_SIZE", "Gundam (Recommended)")

UNLIMITED_SPACE = os.getenv("UNLIMITED_OCR_SPACE", "baidu/Unlimited-OCR")
UNLIMITED_MODE = os.getenv("UNLIMITED_OCR_MODE", "gundam")  # "gundam" (rápido) ou "base" (mais preciso)

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


_clients: dict = {}  # cache por space_id, pra não reconectar a cada chamada


def _get_client(space_id: str) -> Client:
    """Conecta no Space só na primeira vez que ele é usado (não trava o
    startup da API se o Space estiver temporariamente fora do ar)."""
    if space_id not in _clients:
        try:
            _clients[space_id] = Client(space_id)
        except Exception as exc:
            raise OcrIndisponivelError(
                f"Não foi possível conectar no Space de OCR ({space_id}): {exc}"
            ) from exc
    return _clients[space_id]


def _rodar_ocrspace(caminho_imagem: str) -> str:
    """Adaptador pro OCR.space (https://ocr.space/OCRAPI).

    scale=True liga o upscaling interno deles (ajuda bastante em HUD de
    jogo com resolução baixa) e isTable=True garante que o resultado volte
    linha por linha, que é o formato que o nosso parser espera.
    """
    if not OCRSPACE_API_KEY:
        raise OcrIndisponivelError(
            "OCRSPACE_API_KEY não configurada (defina a env var no Render)."
        )

    payload = {
        "apikey": OCRSPACE_API_KEY,
        "language": OCRSPACE_LANGUAGE,
        "OCREngine": OCRSPACE_ENGINE,
        "isOverlayRequired": False,
        "isTable": True,
        "scale": True,
    }

    try:
        with open(caminho_imagem, "rb") as f:
            resposta = requests.post(
                OCRSPACE_ENDPOINT,
                files={"file": f},
                data=payload,
                timeout=30,
            )
        dados = resposta.json()
    except Exception as exc:
        raise OcrIndisponivelError(f"OCR.space não respondeu: {exc}") from exc

    if dados.get("IsErroredOnProcessing"):
        mensagens = dados.get("ErrorMessage") or ["erro desconhecido"]
        raise OcrIndisponivelError(f"OCR.space retornou erro: {'; '.join(mensagens)}")

    resultados = dados.get("ParsedResults") or []
    if not resultados:
        return ""
    return resultados[0].get("ParsedText", "") or ""


def _rodar_deepseek(caminho_imagem: str) -> str:
    """Adaptador pro Space khang119966/DeepSeek-OCR-DEMO (api_name=/process_ocr_task)."""
    client = _get_client(DEEPSEEK_SPACE)
    try:
        texto, _imagem_com_boxes = client.predict(
            image=handle_file(caminho_imagem),
            model_size=DEEPSEEK_MODEL_SIZE,
            task_type="📝 Free OCR",
            ref_text="",
            api_name="/process_ocr_task",
        )
    except Exception as exc:
        raise OcrIndisponivelError(
            f"O Space de OCR ({DEEPSEEK_SPACE}) não respondeu: {exc}"
        ) from exc
    return texto or ""


def _rodar_unlimited(caminho_imagem: str) -> str:
    """Adaptador pro Space baidu/Unlimited-OCR (api_name=/run_ocr).

    ATENÇÃO: essa função ainda NÃO foi validada contra a página "View API"
    real desse Space (a gente só analisou o código-fonte dele, não testou
    a chamada de verdade, diferente do que fizemos com o DeepSeek-OCR).
    Antes de trocar OCR_PROVIDER=unlimited em produção, abra a página do
    Space no Hugging Face → "Use via API" → confirma que os nomes dos
    parâmetros (`image_path`, `mode`, `prompt`) e o `api_name` batem com
    o que está documentado ali, e ajusta aqui se tiver mudado.
    """
    client = _get_client(UNLIMITED_SPACE)
    try:
        resultado = client.predict(
            image_path=handle_file(caminho_imagem),
            mode=UNLIMITED_MODE,
            prompt="document parsing.",
            api_name="/run_ocr",
        )
    except Exception as exc:
        raise OcrIndisponivelError(
            f"O Space de OCR ({UNLIMITED_SPACE}) não respondeu: {exc}"
        ) from exc

    # o endpoint original é um generator que faz streaming — via gradio_client
    # o predict() devolve o último valor emitido, que é um dict {"text","done"}
    if isinstance(resultado, dict):
        return resultado.get("text", "") or ""
    return str(resultado or "")


_PROVEDORES = {
    "ocrspace": _rodar_ocrspace,
    "deepseek": _rodar_deepseek,
    "unlimited": _rodar_unlimited,
}


def _rodar_modelo(caminho_imagem: str) -> str:
    """Manda a imagem pro provedor configurado (OCR_PROVIDER) e devolve o texto bruto."""
    adaptador = _PROVEDORES.get(PROVIDER)
    if adaptador is None:
        raise OcrIndisponivelError(
            f"OCR_PROVIDER='{PROVIDER}' desconhecido. Use 'deepseek' ou 'unlimited'."
        )
    return adaptador(caminho_imagem)


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
    models.py, o site e o bot_integration não precisam mudar nada, seja
    qual for o OCR_PROVIDER configurado.
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

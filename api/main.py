from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from models import OCRResponse, ErrorResponse
from ocr import extrair_medicos_do_print, OcrIndisponivelError

app = FastAPI(
    title="CMS Valley - EMS OCR Service",
    description="Recebe o print do comando EMS e devolve a lista ID:Nome dos médicos em serviço.",
    version="1.0.0",
)

# Ajuste as origens permitidas depois do deploy (domínio do site + o host do bot, se necessário)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Registro central das rotas da API.
#
# O painel (site/) busca essa lista em GET /routes e monta o menu sozinho —
# ou seja, pra adicionar uma ação nova no futuro (ex: comparar com o Discord,
# listar o histórico de chamadas, etc.) basta:
#   1. criar o endpoint normalmente aqui embaixo
#   2. adicionar uma entrada nesta lista
# e o painel já aparece com botão pronto, sem editar nada no HTML/JS.
#
# "tipo" diz ao painel como desenhar a ação:
#   - "status"        -> botão simples "Testar", mostra o JSON cru
#   - "upload_imagem" -> área de drag-and-drop de imagem + resultado em lista
#   - "acao_simples"  -> botão "Executar" que chama a rota sem parâmetros
# ---------------------------------------------------------------------------
ROUTES_INFO = [
    {
        "id": "health",
        "nome": "Status da API",
        "descricao": "Verifica se o serviço está no ar.",
        "method": "GET",
        "path": "/health",
        "tipo": "status",
    },
    {
        "id": "ocr_ems",
        "nome": "Leitor de Chamada EMS",
        "descricao": "Envia o print do comando /ems e recebe a lista ID:Nome dos médicos com toggle ligado.",
        "method": "POST",
        "path": "/ocr/ems",
        "tipo": "upload_imagem",
    },
]


@app.get("/")
def root():
    return RedirectResponse(url="/docs")


@app.get("/routes")
def listar_rotas():
    """Metadados usados pelo painel (site/) pra montar o menu automaticamente."""
    return {"servico": "CMS Valley - EMS OCR", "rotas": ROUTES_INFO}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/ocr/ems",
    response_model=OCRResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def ocr_ems(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de imagem (png/jpg).")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    try:
        resultado = extrair_medicos_do_print(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OcrIndisponivelError as exc:
        # o Space de terceiro que faz o OCR está fora do ar/não respondeu —
        # isso não é um erro do arquivo enviado, é do serviço externo
        raise HTTPException(status_code=503, detail=str(exc))

    return resultado

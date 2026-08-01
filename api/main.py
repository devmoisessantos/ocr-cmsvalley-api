from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import OCRResponse, ErrorResponse
from ocr import extrair_medicos_do_print

app = FastAPI(
    title="CMS Valley - EMS OCR Service",
    description="Recebe o print do comando EMS e devolve a lista ID:Nome dos médicos em serviço.",
    version="1.0.0",
)

# Ajuste as origens permitidas depois do deploy (domínio do site + o host do bot, se necessário)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/ocr/ems",
    response_model=OCRResponse,
    responses={400: {"model": ErrorResponse}},
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

    return resultado

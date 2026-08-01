import re
import os
from typing import List, Tuple

import cv2
import numpy as np
import easyocr

# Idiomas configuráveis por env var (default português)
_LANGS = os.getenv("OCR_LANGS", "pt").split(",")

# EasyOCR é pesado pra inicializar — carrega uma vez só, no import do módulo,
# e reaproveita em todas as requisições.
_reader = easyocr.Reader(_LANGS, gpu=False)

# Casa linhas do tipo "9: Tuco Palacio" ou "62436: GENIN SSA"
_LINE_PATTERN = re.compile(r"^\s*(\d{1,10})\s*[:\-]\s*(.+?)\s*$")


def _preprocess(image_bytes: bytes) -> np.ndarray:
    """Prepara a imagem do print do EMS pra melhorar a leitura do OCR."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Não foi possível decodificar a imagem enviada.")

    # Upscale ajuda o EasyOCR em textos pequenos de HUD de jogo
    h, w = img.shape[:2]
    scale = 2 if max(h, w) < 1200 else 1
    if scale > 1:
        img = cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Contraste adaptativo — o painel do jogo costuma ter texto claro em fundo escuro translúcido
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Binarização adaptativa pra separar texto de fundo com brilho variável
    thresh = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    return thresh


def _parse_lines(raw_lines: List[str]) -> Tuple[List[dict], List[str]]:
    """Separa linhas que batem com o padrão 'ID: Nome' das que não batem."""
    medicos = []
    descartadas = []
    for line in raw_lines:
        match = _LINE_PATTERN.match(line)
        if match:
            id_str, nome = match.groups()
            medicos.append({"id": int(id_str), "nome": nome.strip()})
        else:
            descartadas.append(line)
    return medicos, descartadas


def extrair_medicos_do_print(image_bytes: bytes) -> dict:
    """Recebe os bytes da imagem do print do EMS e devolve a lista ID/Nome."""
    processed = _preprocess(image_bytes)

    resultados = _reader.readtext(processed, detail=0, paragraph=False)

    medicos, descartadas = _parse_lines(resultados)

    aviso = None
    if descartadas:
        aviso = f"{len(descartadas)} linha(s) não reconhecida(s) como 'ID: Nome' e foram ignoradas."

    return {
        "total_detectado": len(medicos),
        "medicos": medicos,
        "aviso": aviso,
    }

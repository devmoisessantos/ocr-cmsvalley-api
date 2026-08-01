from gradio_client import Client, handle_file

client = Client("khang119966/DeepSeek-OCR-DEMO")

resultado = client.predict(
    image=handle_file("static/image.png"),
    model_size="Tiny",  # Tiny, Base, Small, Medium, Large
    task_type="📝 Free OCR",   # texto cru, sem formatação markdown
    ref_text="",
    api_name="/process_ocr_task",
)

texto, imagem_com_boxes = resultado
print(texto)
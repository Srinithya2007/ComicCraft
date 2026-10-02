import json
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.story_generator import generate_story
from services.image_generator import generate_panel_images
from services.exporters import build_comic_pdf


BASE_DIR = Path(__file__).resolve().parent

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
GENERATED_DIR = BASE_DIR / "generated"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="ComicCraft - AI Comic Story Creator",
    version="1.0.0"
)


app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static"
)

app.mount(
    "/generated",
    StaticFiles(directory=str(GENERATED_DIR)),
    name="generated"
)


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR)
)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ComicCraft"
    }


@app.post("/api/generate")
async def generate_comic(
    prompt: str = Form(...),
    character_name: str = Form(...),
    setting: str = Form(...),
    tone: str = Form(...),
    art_style: str = Form(...),
    panels: int = Form(4)
):
    try:
        panels = max(2, min(panels, 8))

        data = {
            "prompt": prompt.strip(),
            "character_name": character_name.strip(),
            "setting": setting.strip(),
            "tone": tone.strip(),
            "art_style": art_style.strip(),
            "panels": panels
        }

        if not data["prompt"]:
            return JSONResponse(
                {"error": "Please enter a story prompt."},
                status_code=400
            )

        if not data["character_name"]:
            return JSONResponse(
                {"error": "Please enter a character name."},
                status_code=400
            )

        if not data["setting"]:
            return JSONResponse(
                {"error": "Please enter a setting."},
                status_code=400
            )

        story = generate_story(data)

        if not isinstance(story, dict):
            return JSONResponse(
                {"error": "Story generator returned invalid data."},
                status_code=500
            )

        if "panels" not in story:
            return JSONResponse(
                {"error": "Generated story does not contain panels."},
                status_code=500
            )

        panel_images = generate_panel_images(
            story,
            data
        )

        if not panel_images:
            return JSONResponse(
                {"error": "No panel images were generated."},
                status_code=500
            )

        comic_id = uuid.uuid4().hex
        image_urls = []

        for index, image_bytes in enumerate(
            panel_images,
            start=1
        ):
            if not isinstance(image_bytes, (bytes, bytearray)):
                return JSONResponse(
                    {
                        "error": f"Invalid image data for panel {index}."
                    },
                    status_code=500
                )

            image_path = (
                GENERATED_DIR /
                f"{comic_id}_panel_{index}.png"
            )

            image_path.write_bytes(image_bytes)

            image_urls.append(
                f"/generated/{image_path.name}"
            )

        for index, panel in enumerate(story["panels"]):
            if index >= len(image_urls):
                break

            if not isinstance(panel, dict):
                story["panels"][index] = {
                    "scene": str(panel),
                    "image_url": image_urls[index]
                }
            else:
                panel["image_url"] = image_urls[index]

        return JSONResponse(
            {
                "comic_id": comic_id,
                "title": story.get(
                    "title",
                    "Untitled Comic"
                ),
                "panels": story["panels"],
                "notice": (
                    "AI-generated creative content. "
                    "Review the story and images before publishing."
                )
            }
        )

    except Exception as exc:
        return JSONResponse(
            {
                "error": f"Comic generation failed: {str(exc)}"
            },
            status_code=500
        )


@app.post("/api/export")
async def export_comic(
    comic_id: str = Form(...),
    title: str = Form(...),
    panels_json: str = Form(...)
):
    try:
        panels = json.loads(panels_json)

    except json.JSONDecodeError:
        return JSONResponse(
            {"error": "Invalid panel data."},
            status_code=400
        )

    if not isinstance(panels, list) or not panels:
        return JSONResponse(
            {"error": "No comic panels supplied."},
            status_code=400
        )

    safe_id = "".join(
        ch for ch in comic_id
        if ch.isalnum()
    )

    if not safe_id:
        return JSONResponse(
            {"error": "Invalid comic ID."},
            status_code=400
        )

    safe_title = title.strip()

    if not safe_title:
        safe_title = "ComicCraft Comic"

    pdf_path = (
        GENERATED_DIR /
        f"ComicCraft_{safe_id}.pdf"
    )

    try:
        build_comic_pdf(
            safe_title,
            panels,
            GENERATED_DIR,
            pdf_path
        )

    except Exception as exc:
        return JSONResponse(
            {
                "error": f"PDF generation failed: {str(exc)}"
            },
            status_code=500
        )

    if not pdf_path.exists():
        return JSONResponse(
            {"error": "PDF file was not created."},
            status_code=500
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name
    )
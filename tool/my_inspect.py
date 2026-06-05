"""
Functions for inspecting outputs in a REPL, useful when debugging
"""

from html import escape
from pathlib import Path
import tool.types as t

# More things worth seeing:
# - The urls beautiful soup return to know when they need to get cleaned

# I want to see if, with a given proxy, it works. Or maybe more simply - I want
# to 

FENDI_ROW = {"vendor": "Fendi", 
                    "product_code": "FW1131AWMMF0QA2", 
                    "quantity" : 1}

MISSONI_ROW = {"vendor": "Missoni", 
                    "product_code": "DC26SN00BK01H2S91RY", 
                    "quantity" : 1}

PAUL_SMITH_ROW = {"vendor": "Paul Smith", 
                    "product_code": "W1R-617N-T11150-92", 
                    "quantity" : 1}

DEBUGGING_AIDS_DIR = Path("debugging_aids")


def _debug_output_path(output_path: str | Path) -> Path:
    output_file = Path(output_path).expanduser()
    if not output_file.is_absolute() and output_file.parts[:1] != (DEBUGGING_AIDS_DIR.name,):
        output_file = DEBUGGING_AIDS_DIR / output_file
    return output_file.resolve()


def _debug_payload(enriched: t.EnrichedOrder) -> t.OrderDebugDict:
    debug = enriched.get("debug")
    if debug is None:
        raise ValueError("Expected enriched order to include debug data.")
    return debug


def _make_html_file(enriched: t.EnrichedOrder, 
                    output_path: str | Path = "reconstructed_html.html") -> Path:
    output_file = _debug_output_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    html = _debug_payload(enriched)["page_data"]["html"]
    output_file.write_text(html, encoding="utf-8")
    return output_file
    
def _extract_candidate_images_as_text(enriched: t.EnrichedOrder,
                                      output_path: str | Path = "candidate_images.txt") -> Path:
    output_file = _debug_output_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    candidates = _debug_payload(enriched)["page_analysis"]["candidate_images"]
    with output_file.open("w", encoding="utf-8") as f:
        for img in candidates:
            idx = img["candidate_index"]
            url = img["src_url"]
            alt = img["alt_text"]
            f.write(f"[{idx}]\nurl: {url}\nalt_text: {alt}\n\n")
    return output_file


def _make_candidate_images_visual_aid(
    enriched: t.EnrichedOrder,
    output_path: str | Path = "candidate_images.html",
) -> Path:
    """
    Write a small HTML gallery for every candidate image in the debug payload.

    Design choices:
        - We intentionally use each candidate image's remote src_url as the
          <img src="..."> target. That means the browser loads the image
          directly from the source site when you open candidate_images.html,
          so this helper does not need to download the assets locally first.
        - We render the candidate index, source URL, alt text, and source page
          URL alongside the actual image so you can visually inspect what the
          scraper handed to the AI.
        - Everything is escaped before being written into HTML except the img
          src/href attribute values, which are still escaped but left as URLs
          so the browser can request them normally.
    """
    output_file = _debug_output_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    page_analysis = _debug_payload(enriched)["page_analysis"]
    candidates = page_analysis["candidate_images"]

    cards = []
    for candidate in candidates:
        idx = candidate.get("candidate_index", "")
        src_url = str(candidate.get("src_url") or "")
        alt_text = candidate.get("alt_text")
        page_url = str(candidate.get("page_url") or "")

        safe_src_url = escape(src_url, quote=True)
        safe_alt_text = escape("" if alt_text is None else str(alt_text))
        safe_page_url = escape(page_url, quote=True)

        if src_url:
            image_block = (
                '<div class="image-frame">'
                f'<img src="{safe_src_url}" alt="{safe_alt_text or "candidate image"}" loading="lazy" />'
                "</div>"
            )
            url_block = (
                f'<a href="{safe_src_url}" target="_blank" rel="noreferrer">{escape(src_url)}</a>'
            )
        else:
            image_block = '<div class="missing-image">Missing src_url</div>'
            url_block = '<span class="muted">Missing</span>'

        if page_url:
            page_url_block = (
                f'<a href="{safe_page_url}" target="_blank" rel="noreferrer">{escape(page_url)}</a>'
            )
        else:
            page_url_block = '<span class="muted">Missing</span>'

        cards.append(
            f"""
            <section class="candidate-card">
              <div class="candidate-header">
                <div class="candidate-index">Candidate {escape(str(idx))}</div>
              </div>
              {image_block}
              <div class="candidate-meta">
                <div class="meta-row">
                  <span class="meta-label">src_url</span>
                  <div class="meta-value">{url_block}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">alt_text</span>
                  <div class="meta-value">{safe_alt_text or '<span class="muted">None</span>'}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">page_url</span>
                  <div class="meta-value">{page_url_block}</div>
                </div>
              </div>
            </section>
            """
        )

    content = "".join(cards) or '<div class="empty-state">No candidate images found in enriched["debug"]["page_analysis"]["candidate_images"]</div>'

    vendor = escape(str(enriched.get("vendor") or "Unknown vendor"))
    product_code = escape(str(enriched.get("product_code") or "Unknown product code"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Candidate Images</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: #fffdf9;
      --ink: #1f1d1a;
      --muted: #6c655d;
      --border: #d7cfc4;
      --link: #17426b;
      --shadow: 0 14px 40px rgba(39, 31, 22, 0.08);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(210, 193, 170, 0.35), transparent 28%),
        linear-gradient(180deg, #f7f2eb 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    .page {{
      width: min(1280px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    .page-header {{
      margin-bottom: 24px;
      padding: 24px;
      border: 1px solid var(--border);
      background: rgba(255, 253, 249, 0.92);
      box-shadow: var(--shadow);
    }}
    .page-header h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 4vw, 40px);
    }}
    .page-header p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .candidate-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
    }}
    .candidate-card {{
      border: 1px solid var(--border);
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    .candidate-header {{
      margin-bottom: 14px;
    }}
    .candidate-index {{
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }}
    .image-frame {{
      display: grid;
      place-items: center;
      min-height: 260px;
      padding: 12px;
      border: 1px solid var(--border);
      background: #fcfaf6;
      margin-bottom: 14px;
    }}
    .image-frame img {{
      display: block;
      max-width: 100%;
      max-height: 360px;
      width: auto;
      height: auto;
      object-fit: contain;
      background: #fff;
    }}
    .candidate-meta {{
      display: grid;
      gap: 12px;
    }}
    .meta-row {{
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }}
    .meta-label {{
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .meta-value {{
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.5;
      word-break: break-word;
    }}
    a {{
      color: var(--link);
    }}
    .missing-image, .empty-state {{
      display: grid;
      place-items: center;
      min-height: 180px;
      border: 1px dashed var(--border);
      background: #f6f1eb;
      color: var(--muted);
      text-align: center;
      padding: 16px;
    }}
    .muted {{
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .page {{
        width: min(100% - 20px, 100%);
        padding-top: 20px;
      }}
      .candidate-card {{
        padding: 14px;
      }}
      .image-frame {{
        min-height: 220px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="page-header">
      <h1>Candidate Images</h1>
      <p>Visual inspection for candidate product images scraped for {vendor} {product_code}.</p>
    </header>
    <div class="candidate-grid">
      {content}
    </div>
  </main>
</body>
</html>
"""
    output_file.write_text(html, encoding="utf-8")
    return output_file


def _make_selected_images_visual_aid(
    enriched: t.EnrichedOrder,
    output_path: str | Path = "selected_images.html",
) -> Path:
    """
    Write a small HTML gallery for the selected `enriched["images"]`.

    Design choices:
        - Prefer local files for display when they exist, since those reflect
          the actual downloaded artifacts we will upload/process later.
        - Fall back to `public_url` and then `src_url` if the local file is
          missing or not present.
        - Show operational fields like local_path, public_url, candidate_index,
          and errors so this page is useful for demo debugging, not just visuals.
    """
    output_file = _debug_output_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    selected_images = enriched.get("images") or []

    cards = []
    for image in selected_images:
        candidate_index = image.get("candidate_index", "")
        src_url = str(image.get("src_url") or "")
        public_url = str(image.get("public_url") or "")
        alt_text = image.get("alt_text")
        page_url = str(image.get("page_url") or "")
        local_path = image.get("local_path")
        errors = image.get("errors") or []
        confidence = image.get("confidence")
        of_a_model = image.get("of_a_model")
        cropped = image.get("cropped")

        local_path_str = ""
        display_src = ""
        if isinstance(local_path, Path):
            local_path_str = str(local_path)
            if local_path.exists():
                display_src = local_path.resolve().as_uri()

        if not display_src and public_url:
            display_src = public_url
        if not display_src and src_url:
            display_src = src_url

        safe_alt_text = escape("" if alt_text is None else str(alt_text))
        safe_src_url = escape(src_url, quote=True)
        safe_public_url = escape(public_url, quote=True)
        safe_page_url = escape(page_url, quote=True)
        safe_local_path = escape(local_path_str)

        if display_src:
            safe_display_src = escape(display_src, quote=True)
            image_block = (
                '<div class="image-frame">'
                f'<img src="{safe_display_src}" alt="{safe_alt_text or "selected image"}" loading="lazy" />'
                "</div>"
            )
        else:
            image_block = '<div class="missing-image">No usable image source found</div>'

        def _link_or_missing(url: str, safe_url: str) -> str:
            if not url:
                return '<span class="muted">Missing</span>'
            return f'<a href="{safe_url}" target="_blank" rel="noreferrer">{escape(url)}</a>'

        local_path_block = safe_local_path or '<span class="muted">Missing</span>'
        public_url_block = _link_or_missing(public_url, safe_public_url)
        src_url_block = _link_or_missing(src_url, safe_src_url)
        page_url_block = _link_or_missing(page_url, safe_page_url)

        if errors:
            errors_html = "<ul>" + "".join(
                f"<li>{escape(str(error))}</li>" for error in errors
            ) + "</ul>"
        else:
            errors_html = '<span class="muted">None</span>'

        confidence_text = '<span class="muted">None</span>' if confidence is None else escape(str(confidence))
        of_model_text = '<span class="muted">None</span>' if of_a_model is None else escape(str(of_a_model))
        cropped_text = '<span class="muted">None</span>' if cropped is None else escape(str(cropped))

        cards.append(
            f"""
            <section class="candidate-card">
              <div class="candidate-header">
                <div class="candidate-index">Selected Image {escape(str(candidate_index))}</div>
              </div>
              {image_block}
              <div class="candidate-meta">
                <div class="meta-row">
                  <span class="meta-label">local_path</span>
                  <div class="meta-value">{local_path_block}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">public_url</span>
                  <div class="meta-value">{public_url_block}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">src_url</span>
                  <div class="meta-value">{src_url_block}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">alt_text</span>
                  <div class="meta-value">{safe_alt_text or '<span class="muted">None</span>'}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">page_url</span>
                  <div class="meta-value">{page_url_block}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">confidence</span>
                  <div class="meta-value">{confidence_text}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">of_a_model</span>
                  <div class="meta-value">{of_model_text}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">cropped</span>
                  <div class="meta-value">{cropped_text}</div>
                </div>
                <div class="meta-row">
                  <span class="meta-label">errors</span>
                  <div class="meta-value">{errors_html}</div>
                </div>
              </div>
            </section>
            """
        )

    content = "".join(cards) or '<div class="empty-state">No selected images found in enriched["images"]</div>'

    vendor = escape(str(enriched.get("vendor") or "Unknown vendor"))
    product_code = escape(str(enriched.get("product_code") or "Unknown product code"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Selected Images</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: #fffdf9;
      --ink: #1f1d1a;
      --muted: #6c655d;
      --border: #d7cfc4;
      --link: #17426b;
      --shadow: 0 14px 40px rgba(39, 31, 22, 0.08);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(210, 193, 170, 0.35), transparent 28%),
        linear-gradient(180deg, #f7f2eb 0%, var(--bg) 100%);
      min-height: 100vh;
    }}
    .page {{
      width: min(1280px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }}
    .page-header {{
      margin-bottom: 24px;
      padding: 24px;
      border: 1px solid var(--border);
      background: rgba(255, 253, 249, 0.92);
      box-shadow: var(--shadow);
    }}
    .page-header h1 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 4vw, 40px);
    }}
    .page-header p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .candidate-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
    }}
    .candidate-card {{
      border: 1px solid var(--border);
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    .candidate-header {{
      margin-bottom: 14px;
    }}
    .candidate-index {{
      font-size: 13px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }}
    .image-frame {{
      display: grid;
      place-items: center;
      min-height: 260px;
      padding: 12px;
      border: 1px solid var(--border);
      background: #fcfaf6;
      margin-bottom: 14px;
    }}
    .image-frame img {{
      display: block;
      max-width: 100%;
      max-height: 360px;
      width: auto;
      height: auto;
      object-fit: contain;
      background: #fff;
    }}
    .candidate-meta {{
      display: grid;
      gap: 12px;
    }}
    .meta-row {{
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }}
    .meta-label {{
      display: block;
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .meta-value {{
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.5;
      word-break: break-word;
    }}
    .meta-value ul {{
      margin: 0;
      padding-left: 18px;
    }}
    a {{
      color: var(--link);
    }}
    .missing-image, .empty-state {{
      display: grid;
      place-items: center;
      min-height: 180px;
      border: 1px dashed var(--border);
      background: #f6f1eb;
      color: var(--muted);
      text-align: center;
      padding: 16px;
    }}
    .muted {{
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .page {{
        width: min(100% - 20px, 100%);
        padding-top: 20px;
      }}
      .candidate-card {{
        padding: 14px;
      }}
      .image-frame {{
        min-height: 220px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="page-header">
      <h1>Selected Images</h1>
      <p>Visual inspection for selected images attached to {vendor} {product_code}.</p>
    </header>
    <div class="candidate-grid">
      {content}
    </div>
  </main>
</body>
</html>
"""
    output_file.write_text(html, encoding="utf-8")
    return output_file

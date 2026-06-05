from html import escape
from pathlib import Path
from typing import Any, Literal, TypeAlias

import tool.types as t

DEBUGGING_AIDS_DIR = Path("debugging_aids")

ImageEntry: TypeAlias = str | t.WeakImage | t.RobustImage
OrderEntry: TypeAlias = t.EnrichedOrder | t.RobustOrder
OrderTableEntry: TypeAlias = t.EnrichedOrderTable | t.RobustOrderTable
Status: TypeAlias = Literal["success", "needs_review", "failed"]


def _debug_output_path(output_path: str | Path) -> Path:
    output_file = Path(output_path).expanduser()
    if not output_file.is_absolute() and output_file.parts[:1] != (DEBUGGING_AIDS_DIR.name,):
        output_file = DEBUGGING_AIDS_DIR / output_file
    return output_file.resolve()


def _status_for_entry(order: OrderEntry) -> Status:
    images = order.get("images") or []
    warnings = [str(w).lower() for w in (order.get("warnings") or [])]
    if not images:
        return "failed"
    if any("404" in warning for warning in warnings):
        return "failed"
    if any("downloading all candidate images" in warning for warning in warnings):
        return "needs_review"
    if len(images) > 10:
        return "needs_review"
    return "success"


def _status_color(status: Status) -> str:
    colors = {
        "success": "#d9f2e3",
        "needs_review": "#fff1bf",
        "failed": "#f7d6d9",
    }
    return colors[status]


def _status_label(status: Status) -> str:
    labels = {
        "success": "success",
        "needs_review": "needs_review",
        "failed": "failed",
    }
    return labels[status]


def _string_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _resolve_local_path(raw_path: str, html_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (html_dir / path).resolve()


def _image_src(raw_path: str, html_dir: Path) -> str | None:
    if not raw_path:
        return None
    if raw_path.startswith(("http://", "https://", "file://")):
        return raw_path
    resolved_path = _resolve_local_path(raw_path, html_dir)
    if not resolved_path.exists():
        return None
    return resolved_path.as_uri()


def _display_path(raw_path: str, html_dir: Path) -> str:
    if not raw_path:
        return ""
    if raw_path.startswith(("http://", "https://", "file://")):
        return raw_path
    return str(_resolve_local_path(raw_path, html_dir))


def _render_main_url(order: OrderEntry) -> str:
    main_url = _string_value(order.get("main_url"), "")
    if not main_url:
        return '<span class="muted">None</span>'
    safe_url = escape(main_url)
    return f'<a href="{safe_url}" target="_blank" rel="noreferrer">{safe_url}</a>'


def _image_reference(image: ImageEntry) -> str:
    if isinstance(image, dict):
        for key in ("local_path", "public_url", "src_url"):
            value = _string_value(image.get(key), "")
            if value:
                return value
        return ""
    return _string_value(image, "")


def _render_image_details(image: ImageEntry) -> str:
    if not isinstance(image, dict):
        return ""

    details: list[str] = []
    candidate_index = image.get("candidate_index")
    if candidate_index is not None:
        details.append(f"candidate_index: {candidate_index}")

    for key in ("alt_text", "src_url", "public_url", "page_url"):
        value = _string_value(image.get(key), "")
        if value:
            details.append(f"{key}: {value}")

    confidence = image.get("confidence")
    if confidence is not None:
        details.append(f"confidence: {confidence}")

    if not details:
        return ""

    lines = "".join(f"<div>{escape(detail)}</div>" for detail in details)
    return f'<div class="image-details">{lines}</div>'


def _render_first_image(images: list[ImageEntry], html_dir: Path) -> str:
    if not images:
        return '<div class="empty-state">No images</div>'

    first_image = images[0]
    first_path = _image_reference(first_image)
    display_path = escape(_display_path(first_path, html_dir))
    image_src = _image_src(first_path, html_dir)
    if not image_src:
        return (
            '<div class="missing-image">'
            '<div class="missing-label">First image file not found</div>'
            f'<div class="file-path">{display_path}</div>'
            f'{_render_image_details(first_image)}'
            "</div>"
        )

    return (
        '<div class="hero-image">'
        f'<img src="{escape(image_src)}" alt="first product image" />'
        f'<div class="file-path">{display_path}</div>'
        f'{_render_image_details(first_image)}'
        "</div>"
    )


def _render_gallery(images: list[ImageEntry], html_dir: Path) -> str:
    if not images:
        return '<div class="empty-state">No images</div>'

    cards: list[str] = []
    for image in images:
        raw_path = _image_reference(image)
        display_path = escape(_display_path(raw_path, html_dir))
        image_src = _image_src(raw_path, html_dir)
        if image_src:
            cards.append(
                '<div class="thumb-card">'
                f'<img src="{escape(image_src)}" alt="product thumbnail" />'
                f'<div class="thumb-path">{display_path}</div>'
                f'{_render_image_details(image)}'
                "</div>"
            )
        else:
            cards.append(
                '<div class="thumb-card missing-thumb">'
                '<div class="missing-label">Missing file</div>'
                f'<div class="thumb-path">{display_path}</div>'
                f'{_render_image_details(image)}'
                "</div>"
            )
    return '<div class="gallery-grid">' + "".join(cards) + "</div>"


def _render_warnings(order: OrderEntry) -> str:
    warnings = order.get("warnings") or []
    if not warnings:
        return '<div class="muted">None</div>'
    items = "".join(f"<li>{escape(str(warning))}</li>" for warning in warnings)
    return f"<ul>{items}</ul>"


def _render_order_card(order: OrderEntry, html_dir: Path, index: int) -> str:
    status = _status_for_entry(order)
    status_color = _status_color(status)
    vendor = escape(_string_value(order.get("vendor"), ""))
    product_code = escape(_string_value(order.get("product_code"), ""))
    quantity = escape(_string_value(order.get("quantity"), ""))
    images: list[ImageEntry] = list(order.get("images") or [])

    return f"""
    <section class="order-card">
      <div class="order-header">
        <div>
          <div class="eyebrow">Order {index}</div>
          <h2>{vendor or "Unknown vendor"}</h2>
        </div>
        <div class="status-pill" style="background:{status_color};">{escape(_status_label(status))}</div>
      </div>
      <div class="meta-grid">
        <div class="meta-item"><span class="meta-label">Vendor</span><span>{vendor or '<span class="muted">Missing</span>'}</span></div>
        <div class="meta-item"><span class="meta-label">Product code</span><span>{product_code or '<span class="muted">Missing</span>'}</span></div>
        <div class="meta-item"><span class="meta-label">Quantity</span><span>{quantity or '<span class="muted">Missing</span>'}</span></div>
      </div>
      <div class="source-block">
        <div class="section-title">Source URL</div>
        <div class="source-link">{_render_main_url(order)}</div>
      </div>
      <div class="image-section">
        <div class="section-title">First image</div>
        {_render_first_image(images, html_dir)}
      </div>
      <div class="image-section">
        <div class="section-title">All images</div>
        {_render_gallery(images, html_dir)}
      </div>
      <div class="warning-section">
        <div class="section-title">Warnings</div>
        {_render_warnings(order)}
      </div>
    </section>
    """


def create_visual_aid(
    data: OrderTableEntry,
    output_path: str | Path = "debug.html",
) -> Path:
    output_file = _debug_output_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    html_dir = output_file.parent

    orders = data.get("orders", [])

    cards = [
        _render_order_card(order, html_dir, index)
        for index, order in enumerate(orders, start=1)
    ]
    content = "".join(cards) or '<div class="empty-page">No orders to display.</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Moda Debug View</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --panel: #fffdf9;
      --ink: #1f1d1a;
      --muted: #6c655d;
      --border: #d7cfc4;
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
      width: min(1200px, calc(100% - 32px));
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
      font-size: clamp(28px, 4vw, 44px);
      letter-spacing: 0.02em;
    }}
    .page-header p {{
      margin: 0;
      color: var(--muted);
      font-size: 16px;
    }}
    .order-card {{
      margin-bottom: 24px;
      padding: 22px;
      border: 1px solid var(--border);
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .order-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 18px;
    }}
    .order-header h2 {{
      margin: 0;
      font-size: 28px;
      line-height: 1.1;
    }}
    .eyebrow {{
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .status-pill {{
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .meta-item, .source-block, .image-section, .warning-section {{
      border: 1px solid var(--border);
      background: #fff;
      padding: 14px;
    }}
    .meta-label, .section-title {{
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .source-link a {{
      color: #17426b;
      word-break: break-word;
    }}
    .hero-image img {{
      display: block;
      max-width: min(100%, 520px);
      max-height: 520px;
      width: auto;
      height: auto;
      border: 1px solid var(--border);
      background: #f8f6f1;
    }}
    .gallery-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
    }}
    .thumb-card {{
      border: 1px solid var(--border);
      padding: 10px;
      background: #fcfaf6;
    }}
    .thumb-card img {{
      display: block;
      width: 100%;
      max-width: 180px;
      max-height: 180px;
      margin: 0 auto 8px;
      object-fit: contain;
      background: #fff;
    }}
    .thumb-path, .file-path {{
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.4;
      color: var(--muted);
      word-break: break-word;
      margin-top: 8px;
    }}
    .image-details {{
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
      font-family: "Courier New", monospace;
      font-size: 12px;
      line-height: 1.45;
      color: var(--muted);
      word-break: break-word;
    }}
    .missing-image, .missing-thumb, .empty-state, .empty-page {{
      display: grid;
      place-items: center;
      min-height: 120px;
      background: #f6f1eb;
      color: var(--muted);
      text-align: center;
    }}
    .missing-label {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .warning-section ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .warning-section li {{
      margin-bottom: 8px;
      line-height: 1.4;
    }}
    .muted {{
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .page {{
        width: min(100% - 20px, 100%);
        padding-top: 20px;
      }}
      .order-card {{
        padding: 16px;
      }}
      .order-header {{
        flex-direction: column;
      }}
      .hero-image img {{
        max-width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="page-header">
      <h1>Moda image debug view</h1>
      <p>Review source pages, first-image quality, warnings, and every downloaded local image in one place.</p>
    </header>
    {content}
  </main>
</body>
</html>
"""
    output_file.write_text(html, encoding="utf-8")
    return output_file

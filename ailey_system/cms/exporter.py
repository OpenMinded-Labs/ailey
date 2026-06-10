"""
Ailey CMS — Static HTML Exporter
==================================
Exports a CMS project as standalone HTML files ready for deployment.
No framework runtime needed — pure HTML + CSS + minimal JS.
"""

import os
import json
import shutil
from typing import Optional

from ailey_system.cms.schema import CMS_BASE, load_project
from ailey_system.cms.renderer import render_page
from ailey_system.cms.legal_generator import generate_legal_pages


def export_static(project_slug: str, output_dir: Optional[str] = None) -> dict:
    """Export a CMS project to static HTML files.

    Returns dict with:
      - success: bool
      - output_dir: str
      - files: list of created files
      - error: str (if failed)
    """
    site = load_project(project_slug)
    if not site:
        return {"success": False, "error": f"Project not found: {project_slug}"}

    if not output_dir:
        output_dir = os.path.join(CMS_BASE, project_slug, "_export")

    # Clean output
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "css"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "js"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "media"), exist_ok=True)

    created_files = []

    try:
        # Render each page
        for page in site.get("pages", []):
            slug = page.get("slug", "/")
            page_html = render_page(site, slug)

            if slug == "/":
                filename = "index.html"
            else:
                filename = slug.strip("/") + ".html"
                # Create subdirectory if needed
                subdir = os.path.dirname(filename)
                if subdir:
                    os.makedirs(os.path.join(output_dir, subdir), exist_ok=True)

            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(page_html)
            created_files.append(filename)

        # Generate legal pages
        legal = generate_legal_pages(site)
        meta = site.get("meta", {})
        design = site.get("design", {})

        for page_name, content_html in [("impressum", legal["impressum_html"]),
                                         ("datenschutz", legal["datenschutz_html"])]:
            page_wrapper = _wrap_legal_page(content_html, page_name.title(), site)
            filepath = os.path.join(output_dir, f"{page_name}.html")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(page_wrapper)
            created_files.append(f"{page_name}.html")

        # Copy media files
        media_src = os.path.join(CMS_BASE, project_slug, "media")
        if os.path.isdir(media_src):
            for item in os.listdir(media_src):
                src = os.path.join(media_src, item)
                dst = os.path.join(output_dir, "media", item)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                    created_files.append(f"media/{item}")

        # Write site.json for re-import
        with open(os.path.join(output_dir, "site.json"), 'w', encoding='utf-8') as f:
            json.dump(site, f, ensure_ascii=False, indent=2)
        created_files.append("site.json")

        # Write custom CSS
        global_css = design.get("globalCSS", "")
        if global_css:
            with open(os.path.join(output_dir, "css", "custom.css"), 'w', encoding='utf-8') as f:
                f.write(global_css)
            created_files.append("css/custom.css")

        return {
            "success": True,
            "output_dir": output_dir,
            "files": created_files,
            "file_count": len(created_files),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def _wrap_legal_page(content_html: str, title: str, site: dict) -> str:
    """Wrap legal content in a full HTML page with site styling."""
    from ailey_system.cms.renderer import render_nav_sticky_transparent, _esc

    meta = site.get("meta", {})
    design = site.get("design", {})
    nav_config = site.get("nav", {})
    colors = design.get("colors", {})
    fonts = design.get("fonts", {})
    heading_font = fonts.get("heading", {}).get("family", "Inter")
    body_font = fonts.get("body", {}).get("family", "Inter")

    google_fonts = set()
    for fconf in fonts.values():
        if fconf.get("source") == "google" and fconf.get("family"):
            google_fonts.add(fconf["family"].replace(" ", "+") + ":wght@300;400;500;600;700")
    font_link = f'<link href="https://fonts.googleapis.com/css2?{"&family=".join(google_fonts)}&display=swap" rel="stylesheet"/>' if google_fonts else ""

    nav_html = render_nav_sticky_transparent(nav_config, design)

    return f'''<!DOCTYPE html>
<html lang="{_esc(meta.get("language", "de"))}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)} — {_esc(meta.get("title",""))}</title>
  {font_link}
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ font-family: '{body_font}', sans-serif; color: {colors.get("text","#1a1a1a")}; background: {colors.get("background","#fff")}; }}
    h1, h2, h3, h4 {{ font-family: '{heading_font}', sans-serif; }}
    .legal-content h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 1.5rem; }}
    .legal-content h2 {{ font-size: 1.5rem; font-weight: 600; margin-top: 2rem; margin-bottom: 0.75rem; }}
    .legal-content h3 {{ font-size: 1.2rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
    .legal-content p {{ margin-bottom: 0.75rem; line-height: 1.7; }}
    .legal-content ul {{ list-style: disc; padding-left: 1.5rem; margin-bottom: 0.75rem; }}
    .legal-content li {{ margin-bottom: 0.25rem; }}
    .legal-content a {{ color: {colors.get("primary","#2563eb")}; text-decoration: underline; }}
  </style>
</head>
<body>
  {nav_html}
  <div style="padding-top:5rem;">
    <div class="max-w-3xl mx-auto px-4 py-12 legal-content">
      {content_html}
    </div>
  </div>
  <script>
    const nav = document.getElementById('main-nav');
    if (nav) {{
      window.addEventListener('scroll', () => {{
        nav.style.background = window.scrollY > 50 ? '{colors.get("background","#fff")}' : 'transparent';
        nav.style.boxShadow = window.scrollY > 50 ? '0 1px 3px rgba(0,0,0,.1)' : 'none';
      }});
    }}
  </script>
</body>
</html>'''

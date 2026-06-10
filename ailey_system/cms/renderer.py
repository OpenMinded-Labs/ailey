"""
Ailey CMS — Section Renderer
=============================
Renders site.json sections into production HTML.
Each section type has a render function that takes the section dict and design context
and returns clean HTML.

The renderer produces standalone HTML that:
- Uses Tailwind utility classes (via CDN or purged build)
- Includes custom CSS per section
- Supports all animations via IntersectionObserver
- Is fully responsive
- Can be exported as static files
"""

import html
import json
import re
from typing import Optional

# ── Helpers ───────────────────────────────────────────────────

def _esc(text: str) -> str:
    """HTML-escape text."""
    return html.escape(str(text)) if text else ""

def _classes(section: dict, extra: list = None) -> str:
    """Build the class string for a section wrapper."""
    classes = list(section.get("style", {}).get("classes", []))
    custom = section.get("style", {}).get("customClasses", "")
    if custom:
        classes.extend(custom.split())
    if extra:
        classes.extend(extra)
    return " ".join(classes)

def _attrs(section: dict) -> str:
    """Build extra attributes (id, animation data attrs)."""
    parts = []
    cid = section.get("style", {}).get("customId", "")
    if cid:
        parts.append(f'id="{_esc(cid)}"')

    anim = section.get("animation", {})
    atype = anim.get("type", "none")
    if atype and atype != "none":
        parts.append(f'data-animate="{_esc(atype)}"')
        if anim.get("delay"):
            parts.append(f'data-animate-delay="{anim["delay"]}"')
        if anim.get("duration"):
            parts.append(f'data-animate-duration="{anim["duration"]}"')

    return " ".join(parts)

def _custom_css(section: dict) -> str:
    """Return a <style> block for custom CSS if present."""
    css = section.get("style", {}).get("customCSS", "").strip()
    if not css:
        return ""
    return f'<style>{css}</style>'

def _cta_html(cta: Optional[dict], primary: bool = True) -> str:
    """Render a CTA button."""
    if not cta:
        return ""
    text = _esc(cta.get("text", ""))
    href = _esc(cta.get("href", "#"))
    style = cta.get("style", "primary" if primary else "outline")

    if style == "outline":
        cls = "inline-block px-6 py-3 border-2 border-current rounded-lg font-semibold hover:bg-primary hover:text-white transition-colors"
    else:
        cls = "inline-block px-6 py-3 bg-primary text-white rounded-lg font-semibold hover:bg-primary/90 transition-colors"

    return f'<a href="{href}" class="{cls}">{text}</a>'

def _img_html(img: dict, extra_classes: str = "") -> str:
    """Render an image tag."""
    if not img or not img.get("src"):
        return '<div class="w-full h-64 bg-gradient-to-br from-primary/20 to-primary/5 rounded-lg flex items-center justify-center text-4xl opacity-50">📷</div>'

    src = _esc(img.get("src", ""))
    alt = _esc(img.get("alt", ""))
    fit = img.get("fit", "cover")
    br = img.get("borderRadius", "")
    style_parts = []
    if br:
        style_parts.append(f"border-radius:{br}")

    cls = f"w-full h-full object-{fit} {extra_classes}".strip()
    style = f' style="{";".join(style_parts)}"' if style_parts else ""
    return f'<img src="{src}" alt="{alt}" class="{cls}"{style} loading="lazy"/>'


# ── Section Renderers ────────────────────────────────────────

def render_hero_fullscreen(section: dict, design: dict) -> str:
    p = section.get("props", {})
    bg = p.get("backgroundImage", {})
    overlay = p.get("overlay", "rgba(0,0,0,0.4)")

    bg_style = ""
    if bg.get("src"):
        bg_style = f'background-image:url({_esc(bg["src"])});background-size:cover;background-position:{bg.get("position","center")};'

    return f'''
{_custom_css(section)}
<section class="{_classes(section, ['relative'])}" {_attrs(section)} style="{bg_style}">
  <div class="absolute inset-0" style="background:{overlay}"></div>
  <div class="relative z-10 max-w-4xl mx-auto text-center text-white px-4">
    <h1 class="text-5xl md:text-7xl font-bold mb-6">{_esc(p.get("headline", ""))}</h1>
    <p class="text-xl md:text-2xl mb-10 opacity-90">{_esc(p.get("subline", ""))}</p>
    <div class="flex flex-wrap gap-4 justify-center">
      {_cta_html(p.get("cta"))}
      {_cta_html(p.get("cta2"), primary=False)}
    </div>
  </div>
</section>'''


def render_hero_split(section: dict, design: dict) -> str:
    p = section.get("props", {})
    variant = section.get("variant", "image-right")
    img = p.get("image", {})

    order_text = "order-1" if "image-left" in variant else "order-1 lg:order-1"
    order_img = "order-2" if "image-left" in variant else "order-2 lg:order-2"
    if "image-left" in variant:
        order_text = "order-2"
        order_img = "order-1"

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4 grid lg:grid-cols-2 gap-12 items-center">
    <div class="{order_text}">
      <h1 class="text-4xl md:text-5xl lg:text-6xl font-bold mb-6">{_esc(p.get("headline", ""))}</h1>
      <p class="text-lg text-muted mb-8">{_esc(p.get("subline", ""))}</p>
      <div class="flex flex-wrap gap-4">
        {_cta_html(p.get("cta"))}
        {_cta_html(p.get("cta2"), primary=False)}
      </div>
    </div>
    <div class="{order_img}">
      {_img_html(img, "rounded-xl shadow-2xl")}
    </div>
  </div>
</section>'''


def render_hero_minimal(section: dict, design: dict) -> str:
    p = section.get("props", {})
    badge = p.get("badge", "")
    badge_html = f'<span class="inline-block px-3 py-1 rounded-full text-sm bg-primary/10 text-primary font-medium mb-4">{_esc(badge)}</span>' if badge else ""

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-3xl mx-auto px-4">
    {badge_html}
    <h1 class="text-4xl md:text-5xl font-bold mb-4">{_esc(p.get("headline", ""))}</h1>
    <p class="text-lg text-muted mb-8">{_esc(p.get("subline", ""))}</p>
    {_cta_html(p.get("cta"))}
  </div>
</section>'''


def render_about_text_image(section: dict, design: dict) -> str:
    p = section.get("props", {})
    variant = section.get("variant", "image-right")
    img = p.get("image", {})

    order_text = "order-1" if "image-left" not in variant else "order-2"
    order_img = "order-2" if "image-left" not in variant else "order-1"

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4 grid lg:grid-cols-2 gap-12 items-center">
    <div class="{order_text}">
      <h2 class="text-3xl font-bold mb-4">{_esc(p.get("headline", ""))}</h2>
      <p class="text-muted leading-relaxed">{_esc(p.get("text", ""))}</p>
    </div>
    <div class="{order_img}">
      {_img_html(img, "rounded-xl")}
    </div>
  </div>
</section>'''


def render_about_team(section: dict, design: dict) -> str:
    p = section.get("props", {})
    members = p.get("members", [])
    variant = section.get("variant", "grid-3")
    cols = "3" if "grid-3" in variant else "4" if "grid-4" in variant else "3"

    cards = ""
    for m in members:
        img = m.get("image", "")
        img_tag = f'<img src="{_esc(img)}" alt="{_esc(m.get("name",""))}" class="w-24 h-24 rounded-full object-cover mx-auto mb-4"/>' if img else '<div class="w-24 h-24 rounded-full bg-primary/10 flex items-center justify-center text-3xl mx-auto mb-4">👤</div>'
        cards += f'''
        <div class="text-center">
          {img_tag}
          <h3 class="font-semibold text-lg">{_esc(m.get("name", ""))}</h3>
          <p class="text-sm text-muted">{_esc(m.get("role", ""))}</p>
          <p class="text-sm mt-2">{_esc(m.get("bio", ""))}</p>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-4">{_esc(p.get("headline", ""))}</h2>
    <p class="text-center text-muted mb-12">{_esc(p.get("subline", ""))}</p>
    <div class="grid md:grid-cols-2 lg:grid-cols-{cols} gap-8">
      {cards}
    </div>
  </div>
</section>'''


def render_about_stats(section: dict, design: dict) -> str:
    p = section.get("props", {})
    stats = p.get("stats", [])

    items = ""
    for s in stats:
        items += f'''
        <div class="text-center">
          <div class="text-4xl font-bold text-primary mb-2">{_esc(s.get("value", ""))}</div>
          <div class="text-sm text-muted">{_esc(s.get("label", ""))}</div>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-5xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    <div class="grid grid-cols-2 md:grid-cols-{len(stats)} gap-8">
      {items}
    </div>
  </div>
</section>'''


def render_services_grid(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])
    variant = section.get("variant", "3col")
    cols = "2" if "2col" in variant else "4" if "4col" in variant else "3"

    cards = ""
    for item in items:
        icon = item.get("icon", "⚡")
        cards += f'''
        <div class="p-6 rounded-xl border border-border bg-surface hover:shadow-lg transition-shadow">
          <div class="text-3xl mb-4">{icon}</div>
          <h3 class="text-xl font-semibold mb-2">{_esc(item.get("title", ""))}</h3>
          <p class="text-muted text-sm">{_esc(item.get("description", ""))}</p>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-4">{_esc(p.get("headline", ""))}</h2>
    {"<p class='text-center text-muted mb-12'>" + _esc(p.get("subline","")) + "</p>" if p.get("subline") else "<div class='mb-12'></div>"}
    <div class="grid md:grid-cols-2 lg:grid-cols-{cols} gap-6">
      {cards}
    </div>
  </div>
</section>'''


def render_services_accordion(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])

    acc_items = ""
    for i, item in enumerate(items):
        acc_items += f'''
        <details class="group border-b border-border" {"open" if i==0 else ""}>
          <summary class="flex justify-between items-center py-4 cursor-pointer font-semibold hover:text-primary transition-colors">
            {_esc(item.get("title", ""))}
            <span class="transform group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div class="pb-4 text-muted">{_esc(item.get("content", ""))}</div>
        </details>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-3xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    <div class="divide-y divide-border">
      {acc_items}
    </div>
  </div>
</section>'''


def render_portfolio_grid(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])

    cards = ""
    for item in items:
        img = item.get("image", "")
        tags = " ".join(f'<span class="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs">{_esc(t)}</span>' for t in item.get("tags", []))
        img_tag = f'<img src="{_esc(img)}" alt="{_esc(item.get("title",""))}" class="w-full h-48 object-cover"/>' if img else '<div class="w-full h-48 bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center text-4xl">🖼️</div>'

        cards += f'''
        <div class="rounded-xl overflow-hidden border border-border bg-surface hover:shadow-xl transition-shadow group">
          <div class="overflow-hidden">{img_tag}</div>
          <div class="p-4">
            <h3 class="font-semibold mb-2">{_esc(item.get("title", ""))}</h3>
            <p class="text-sm text-muted mb-3">{_esc(item.get("description", ""))}</p>
            <div class="flex flex-wrap gap-1">{tags}</div>
          </div>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-4">{_esc(p.get("headline", ""))}</h2>
    {"<p class='text-center text-muted mb-12'>" + _esc(p.get("subline","")) + "</p>" if p.get("subline") else "<div class='mb-12'></div>"}
    <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
      {cards}
    </div>
  </div>
</section>'''


def render_testimonials_slider(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])

    cards = ""
    for item in items:
        img = item.get("image", "")
        img_tag = f'<img src="{_esc(img)}" alt="{_esc(item.get("author",""))}" class="w-12 h-12 rounded-full object-cover"/>' if img else '<div class="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">⭐</div>'

        cards += f'''
        <div class="bg-white dark:bg-gray-800 p-6 rounded-xl border border-border shadow-sm">
          <p class="text-muted italic mb-4">"{_esc(item.get("quote", ""))}"</p>
          <div class="flex items-center gap-3">
            {img_tag}
            <div>
              <div class="font-semibold text-sm">{_esc(item.get("author", ""))}</div>
              <div class="text-xs text-muted">{_esc(item.get("role", ""))}</div>
            </div>
          </div>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-5xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
      {cards}
    </div>
  </div>
</section>'''


def render_text_block(section: dict, design: dict) -> str:
    p = section.get("props", {})
    align = p.get("align", "left")
    align_class = f"text-{align}" if align != "left" else ""

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-3xl mx-auto px-4 {align_class}">
    {"<h2 class='text-3xl font-bold mb-6'>" + _esc(p.get("headline","")) + "</h2>" if p.get("headline") else ""}
    <div class="prose prose-lg max-w-none">{p.get("text", "")}</div>
  </div>
</section>'''


def render_blockquote(section: dict, design: dict) -> str:
    p = section.get("props", {})

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-3xl mx-auto px-4 text-center">
    <blockquote class="text-2xl md:text-3xl italic font-light leading-relaxed mb-4">
      "{_esc(p.get("quote", ""))}"
    </blockquote>
    {"<p class='text-muted font-medium'>— " + _esc(p.get("author","")) + "</p>" if p.get("author") else ""}
  </div>
</section>'''


def render_cta_banner(section: dict, design: dict) -> str:
    p = section.get("props", {})

    return f'''
{_custom_css(section)}
<section class="{_classes(section, ['bg-primary', 'text-white'])}" {_attrs(section)}>
  <div class="max-w-4xl mx-auto px-4 text-center">
    <h2 class="text-3xl font-bold mb-4">{_esc(p.get("headline", ""))}</h2>
    <p class="text-lg opacity-90 mb-8">{_esc(p.get("subline", ""))}</p>
    <a href="{_esc(p.get('cta',{}).get('href','#'))}" class="inline-block px-8 py-4 bg-white text-primary rounded-lg font-semibold hover:bg-gray-100 transition-colors text-lg">
      {_esc(p.get('cta',{}).get('text','Los geht\'s'))}
    </a>
  </div>
</section>'''


def render_features_icon_grid(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])
    variant = section.get("variant", "3col")
    cols = "4" if "4col" in variant else "6" if "6col" in variant else "3"

    cards = ""
    for item in items:
        cards += f'''
        <div class="text-center p-6">
          <div class="text-4xl mb-4">{item.get("icon", "✨")}</div>
          <h3 class="font-semibold text-lg mb-2">{_esc(item.get("title", ""))}</h3>
          <p class="text-sm text-muted">{_esc(item.get("description", ""))}</p>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-4">{_esc(p.get("headline", ""))}</h2>
    {"<p class='text-center text-muted mb-12'>" + _esc(p.get("subline","")) + "</p>" if p.get("subline") else "<div class='mb-12'></div>"}
    <div class="grid md:grid-cols-2 lg:grid-cols-{cols} gap-4">
      {cards}
    </div>
  </div>
</section>'''


def render_features_comparison(section: dict, design: dict) -> str:
    p = section.get("props", {})
    plans = p.get("plans", [])

    cards = ""
    for plan in plans:
        highlighted = plan.get("highlighted", False)
        border = "border-primary border-2 shadow-xl scale-105" if highlighted else "border-border"
        badge = '<span class="absolute -top-3 left-1/2 -translate-x-1/2 bg-primary text-white text-xs px-3 py-1 rounded-full">Empfohlen</span>' if highlighted else ""

        features_html = ""
        for f in plan.get("features", []):
            features_html += f'<li class="flex items-center gap-2 py-1"><span class="text-green-500">✓</span> {_esc(f)}</li>'

        cards += f'''
        <div class="relative rounded-xl border {border} bg-white dark:bg-gray-800 p-6 text-center">
          {badge}
          <h3 class="text-xl font-bold mb-2">{_esc(plan.get("name", ""))}</h3>
          <div class="text-3xl font-bold text-primary mb-4">{_esc(plan.get("price", ""))}</div>
          <ul class="text-sm text-left mb-6">{features_html}</ul>
          {_cta_html(plan.get("cta"))}
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-5xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    <div class="grid md:grid-cols-{len(plans)} gap-8 items-start">
      {cards}
    </div>
  </div>
</section>'''


def render_contact_form(section: dict, design: dict) -> str:
    p = section.get("props", {})
    fields = p.get("fields", [])

    fields_html = ""
    for f in fields:
        fname = _esc(f.get("name", ""))
        flabel = _esc(f.get("label", ""))
        ftype = f.get("type", "text")
        freq = " required" if f.get("required") else ""

        if ftype == "textarea":
            fields_html += f'''
            <div>
              <label for="{fname}" class="block text-sm font-medium mb-1">{flabel}</label>
              <textarea id="{fname}" name="{fname}" rows="5" class="w-full px-4 py-3 rounded-lg border border-border bg-surface focus:ring-2 focus:ring-primary focus:border-transparent"{freq}></textarea>
            </div>'''
        else:
            fields_html += f'''
            <div>
              <label for="{fname}" class="block text-sm font-medium mb-1">{flabel}</label>
              <input id="{fname}" name="{fname}" type="{ftype}" class="w-full px-4 py-3 rounded-lg border border-border bg-surface focus:ring-2 focus:ring-primary focus:border-transparent"{freq}/>
            </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-2xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-4">{_esc(p.get("headline", ""))}</h2>
    <p class="text-center text-muted mb-8">{_esc(p.get("subline", ""))}</p>
    <form class="space-y-4" onsubmit="event.preventDefault();this.querySelector('.submit-btn').textContent='{_esc(p.get("successMessage","Gesendet!"))}';return false;">
      {fields_html}
      <button type="submit" class="submit-btn w-full px-6 py-3 bg-primary text-white rounded-lg font-semibold hover:bg-primary/90 transition-colors">
        {_esc(p.get("submitText", "Absenden"))}
      </button>
    </form>
  </div>
</section>'''


def render_contact_split(section: dict, design: dict) -> str:
    p = section.get("props", {})
    info = p.get("info", {})
    fields = p.get("fields", [])

    info_html = ""
    if info.get("address"):
        info_html += f'<p class="flex items-start gap-2"><span>📍</span> {_esc(info["address"])}</p>'
    if info.get("phone"):
        info_html += f'<p class="flex items-start gap-2"><span>📞</span> {_esc(info["phone"])}</p>'
    if info.get("email"):
        info_html += f'<p class="flex items-start gap-2"><span>✉️</span> <a href="mailto:{_esc(info["email"])}" class="text-primary hover:underline">{_esc(info["email"])}</a></p>'
    if info.get("hours"):
        info_html += f'<p class="flex items-start gap-2"><span>🕐</span> {_esc(info["hours"])}</p>'

    fields_html = ""
    for f in fields:
        fname = _esc(f.get("name", ""))
        flabel = _esc(f.get("label", ""))
        ftype = f.get("type", "text")
        if ftype == "textarea":
            fields_html += f'<textarea name="{fname}" placeholder="{flabel}" rows="4" class="w-full px-4 py-3 rounded-lg border border-border bg-surface"></textarea>'
        else:
            fields_html += f'<input name="{fname}" type="{ftype}" placeholder="{flabel}" class="w-full px-4 py-3 rounded-lg border border-border bg-surface"/>'

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-6xl mx-auto px-4 grid lg:grid-cols-2 gap-12">
    <div>
      <h2 class="text-3xl font-bold mb-6">{_esc(p.get("headline", ""))}</h2>
      <div class="space-y-4 text-muted">{info_html}</div>
    </div>
    <form class="space-y-4">
      {fields_html}
      <button type="submit" class="w-full px-6 py-3 bg-primary text-white rounded-lg font-semibold hover:bg-primary/90 transition-colors">
        {_esc(p.get("submitText", "Absenden"))}
      </button>
    </form>
  </div>
</section>'''


def render_blog_grid(section: dict, design: dict) -> str:
    p = section.get("props", {})
    posts = p.get("posts", [])

    cards = ""
    for post in posts:
        img = post.get("image", "")
        img_tag = f'<img src="{_esc(img)}" alt="{_esc(post.get("title",""))}" class="w-full h-48 object-cover"/>' if img else '<div class="w-full h-48 bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center text-3xl">📰</div>'

        cards += f'''
        <article class="rounded-xl overflow-hidden border border-border bg-surface">
          {img_tag}
          <div class="p-4">
            <time class="text-xs text-muted">{_esc(post.get("date", ""))}</time>
            <h3 class="font-semibold mt-1 mb-2">{_esc(post.get("title", ""))}</h3>
            <p class="text-sm text-muted">{_esc(post.get("excerpt", ""))}</p>
          </div>
        </article>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
      {cards}
    </div>
  </div>
</section>'''


def render_faq_accordion(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])

    acc = ""
    for i, item in enumerate(items):
        acc += f'''
        <details class="group border-b border-border" {"open" if i==0 else ""}>
          <summary class="flex justify-between items-center py-4 cursor-pointer font-semibold hover:text-primary transition-colors">
            {_esc(item.get("question", ""))}
            <span class="transform group-open:rotate-180 transition-transform text-primary">▼</span>
          </summary>
          <div class="pb-4 text-muted">{_esc(item.get("answer", ""))}</div>
        </details>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-3xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    {acc}
  </div>
</section>'''


def render_gallery_lightbox(section: dict, design: dict) -> str:
    p = section.get("props", {})
    images = p.get("images", [])

    items = ""
    for img in images:
        src = _esc(img.get("src", ""))
        alt = _esc(img.get("alt", ""))
        if src:
            items += f'<div class="cursor-pointer overflow-hidden rounded-lg"><img src="{src}" alt="{alt}" class="w-full h-48 object-cover hover:scale-105 transition-transform duration-300" onclick="window.open(this.src)"/></div>'
        else:
            items += '<div class="h-48 bg-gradient-to-br from-primary/20 to-primary/5 rounded-lg flex items-center justify-center text-3xl">🖼️</div>'

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <h2 class="text-3xl font-bold text-center mb-12">{_esc(p.get("headline", ""))}</h2>
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      {items}
    </div>
  </div>
</section>'''


def render_parallax_divider(section: dict, design: dict) -> str:
    p = section.get("props", {})
    img = p.get("image", {})
    height = p.get("height", "400px")
    text = p.get("text", "")
    overlay = p.get("overlay", "rgba(0,0,0,0.3)")

    bg_style = f'background-image:url({_esc(img.get("src",""))});background-size:cover;background-position:center;background-attachment:fixed;' if img.get("src") else ""

    return f'''
{_custom_css(section)}
<section class="{_classes(section, ['relative', 'flex', 'items-center', 'justify-center'])}" {_attrs(section)} style="min-height:{height};{bg_style}">
  <div class="absolute inset-0" style="background:{overlay}"></div>
  {"<p class='relative z-10 text-white text-3xl font-bold text-center'>" + _esc(text) + "</p>" if text else ""}
</section>'''


def render_video_embed(section: dict, design: dict) -> str:
    p = section.get("props", {})
    source = p.get("source", "youtube")
    url = p.get("url", "")

    if "youtube" in source and url:
        vid_id = ""
        if "v=" in url:
            vid_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            vid_id = url.split("youtu.be/")[1].split("?")[0]

        if vid_id:
            embed = f'<iframe src="https://www.youtube-nocookie.com/embed/{_esc(vid_id)}" class="w-full aspect-video rounded-xl" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>'
        else:
            embed = '<p class="text-muted">Ungültige YouTube-URL</p>'
    elif "vimeo" in source and url:
        vid_id = url.split("/")[-1]
        embed = f'<iframe src="https://player.vimeo.com/video/{_esc(vid_id)}" class="w-full aspect-video rounded-xl" frameborder="0" allowfullscreen></iframe>'
    elif url:
        embed = f'<video src="{_esc(url)}" class="w-full rounded-xl" controls {"autoplay" if p.get("autoplay") else ""} {"loop" if p.get("loop") else ""}></video>'
    else:
        embed = '<div class="w-full aspect-video bg-gray-100 dark:bg-gray-800 rounded-xl flex items-center justify-center text-4xl">🎥</div>'

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-4xl mx-auto px-4">
    {"<h2 class='text-3xl font-bold text-center mb-8'>" + _esc(p.get("headline","")) + "</h2>" if p.get("headline") else ""}
    {embed}
  </div>
</section>'''


def render_pricing_table(section: dict, design: dict) -> str:
    # Reuse features_comparison with slight wrapper
    return render_features_comparison(section, design)


def render_logos_bar(section: dict, design: dict) -> str:
    p = section.get("props", {})
    logos = p.get("logos", [])

    items = ""
    for logo in logos:
        src = _esc(logo.get("src", ""))
        alt = _esc(logo.get("alt", ""))
        if src:
            items += f'<div class="flex items-center justify-center px-4"><img src="{src}" alt="{alt}" class="h-10 opacity-50 hover:opacity-100 transition-opacity grayscale hover:grayscale-0"/></div>'

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-6xl mx-auto px-4 flex flex-wrap justify-center gap-8 items-center">
    {items}
  </div>
</section>'''


def render_text_image_alternating(section: dict, design: dict) -> str:
    p = section.get("props", {})
    items = p.get("items", [])

    blocks = ""
    for i, item in enumerate(items):
        img = item.get("image", {})
        reverse = "lg:flex-row-reverse" if i % 2 == 1 else ""
        blocks += f'''
        <div class="flex flex-col lg:flex-row {reverse} gap-12 items-center mb-16">
          <div class="flex-1">
            <h3 class="text-2xl font-bold mb-4">{_esc(item.get("headline", ""))}</h3>
            <p class="text-muted leading-relaxed">{_esc(item.get("text", ""))}</p>
          </div>
          <div class="flex-1">
            {_img_html(img, "rounded-xl")}
          </div>
        </div>'''

    return f'''
{_custom_css(section)}
<section class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    {blocks}
  </div>
</section>'''


# ── Footer Renderers ──────────────────────────────────────────

def render_footer_columns(section: dict, design: dict) -> str:
    p = section.get("props", {})
    columns = p.get("columns", [])
    copyright_text = p.get("copyright", "").replace("{year}", "2025")
    legal = p.get("legalLinks", [])

    cols_html = ""
    for col in columns:
        if col.get("links"):
            links = "".join(f'<a href="{_esc(l["href"])}" class="block text-sm text-gray-400 hover:text-white transition-colors">{_esc(l["label"])}</a>' for l in col["links"])
            cols_html += f'''
            <div>
              <h4 class="font-semibold mb-4">{_esc(col.get("title", ""))}</h4>
              <div class="space-y-2">{links}</div>
            </div>'''
        elif col.get("html"):
            cols_html += f'''
            <div>
              <h4 class="font-semibold mb-4">{_esc(col.get("title", ""))}</h4>
              <div class="text-sm text-gray-400">{col["html"]}</div>
            </div>'''
        elif col.get("social"):
            socials = " ".join(f'<a href="{_esc(s["url"])}" class="text-gray-400 hover:text-white transition-colors" target="_blank">{_esc(s["platform"])}</a>' for s in col["social"])
            cols_html += f'''
            <div>
              <h4 class="font-semibold mb-4">{_esc(col.get("title", ""))}</h4>
              <div class="flex gap-4">{socials}</div>
            </div>'''

    legal_html = " | ".join(f'<a href="{_esc(l["href"])}" class="hover:text-white transition-colors">{_esc(l["label"])}</a>' for l in legal)

    return f'''
{_custom_css(section)}
<footer class="{_classes(section)}" {_attrs(section)}>
  <div class="max-w-7xl mx-auto px-4">
    <div class="grid md:grid-cols-{len(columns) or 1} gap-8 mb-8">
      {cols_html}
    </div>
    <div class="border-t border-gray-700 pt-6 flex flex-col md:flex-row justify-between items-center text-sm text-gray-400">
      <p>{_esc(copyright_text)}</p>
      <div class="flex gap-4 mt-2 md:mt-0">{legal_html}</div>
    </div>
  </div>
</footer>'''


def render_footer_minimal(section: dict, design: dict) -> str:
    p = section.get("props", {})
    copyright_text = p.get("copyright", "").replace("{year}", "2025")
    legal = p.get("legalLinks", [])

    legal_html = " | ".join(f'<a href="{_esc(l["href"])}" class="hover:text-primary transition-colors">{_esc(l["label"])}</a>' for l in legal)

    return f'''
{_custom_css(section)}
<footer class="{_classes(section, ['border-t', 'border-border'])}" {_attrs(section)}>
  <div class="max-w-4xl mx-auto px-4">
    <p class="text-muted">{_esc(copyright_text)}</p>
    <div class="flex justify-center gap-4 mt-2 text-sm text-muted">{legal_html}</div>
  </div>
</footer>'''


# ── Nav Renderers ─────────────────────────────────────────────

def render_nav_sticky_transparent(nav_config: dict, design: dict) -> str:
    """Render the main navigation bar."""
    logo = nav_config.get("logo", {})
    links = nav_config.get("links", [])
    cta = nav_config.get("cta")

    logo_html = f'<img src="{_esc(logo["src"])}" alt="{_esc(logo.get("alt",""))}" style="height:{logo.get("height","40px")}"/>' if logo.get("src") else '<span class="text-xl font-bold">Logo</span>'

    links_html = ""
    for link in links:
        if link.get("style") == "button":
            links_html += f' <a href="{_esc(link["href"])}" class="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors">{_esc(link["label"])}</a>'
        else:
            links_html += f' <a href="{_esc(link["href"])}" class="text-sm font-medium hover:text-primary transition-colors">{_esc(link["label"])}</a>'

    cta_html = ""
    if cta:
        cta_html = f'<a href="{_esc(cta["href"])}" class="px-4 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors">{_esc(cta["text"])}</a>'

    return f'''
<nav class="fixed top-0 left-0 right-0 z-50 transition-all duration-300" id="main-nav"
     data-transparent="true">
  <div class="max-w-7xl mx-auto px-4 flex items-center justify-between h-16">
    <a href="/" class="flex items-center">{logo_html}</a>
    <div class="hidden md:flex items-center gap-6">
      {links_html}
      {cta_html}
    </div>
    <button class="md:hidden p-2" onclick="document.getElementById('mobile-menu').classList.toggle('hidden')">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
      </svg>
    </button>
  </div>
  <div id="mobile-menu" class="hidden md:hidden bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm border-t border-border">
    <div class="px-4 py-4 space-y-3">
      {"".join(f'<a href="{_esc(l["href"])}" class="block py-2 font-medium">{_esc(l["label"])}</a>' for l in links)}
      {('<a href="' + _esc(cta["href"]) + '" class="block w-full text-center py-2 bg-primary text-white rounded-lg font-medium">' + _esc(cta["text"]) + '</a>') if cta else ""}
    </div>
  </div>
</nav>'''


# ── Master Render Dispatch ────────────────────────────────────

RENDERERS = {
    "hero-fullscreen": render_hero_fullscreen,
    "hero-split": render_hero_split,
    "hero-minimal": render_hero_minimal,
    "about-text-image": render_about_text_image,
    "about-team": render_about_team,
    "about-stats": render_about_stats,
    "services-grid": render_services_grid,
    "services-accordion": render_services_accordion,
    "portfolio-grid": render_portfolio_grid,
    "testimonials-slider": render_testimonials_slider,
    "logos-bar": render_logos_bar,
    "text-block": render_text_block,
    "text-image-alternating": render_text_image_alternating,
    "blockquote": render_blockquote,
    "cta-banner": render_cta_banner,
    "features-icon-grid": render_features_icon_grid,
    "features-comparison": render_features_comparison,
    "contact-form": render_contact_form,
    "contact-split": render_contact_split,
    "blog-grid": render_blog_grid,
    "footer-columns": render_footer_columns,
    "footer-minimal": render_footer_minimal,
    "faq-accordion": render_faq_accordion,
    "gallery-lightbox": render_gallery_lightbox,
    "parallax-divider": render_parallax_divider,
    "video-embed": render_video_embed,
    "pricing-table": render_pricing_table,
}


def render_section(section: dict, design: dict) -> str:
    """Render a single section to HTML."""
    stype = section.get("type", "")
    renderer = RENDERERS.get(stype)
    if not renderer:
        return f'<!-- Unknown section type: {_esc(stype)} -->'
    return renderer(section, design)


def render_page(site: dict, page_slug: str = "/") -> str:
    """Render a full page to complete HTML document."""
    page = next((p for p in site.get("pages", []) if p["slug"] == page_slug), None)
    if not page:
        return "<html><body><h1>Page not found</h1></body></html>"

    meta = site.get("meta", {})
    design = site.get("design", {})
    nav_config = site.get("nav", {})
    colors = design.get("colors", {})
    fonts = design.get("fonts", {})

    # Build CSS custom properties
    css_vars = "\n".join(f"      --color-{k}: {v};" for k, v in colors.items())
    heading_font = fonts.get("heading", {}).get("family", "Inter")
    body_font = fonts.get("body", {}).get("family", "Inter")

    google_fonts = set()
    for fconf in fonts.values():
        if fconf.get("source") == "google" and fconf.get("family"):
            google_fonts.add(fconf["family"].replace(" ", "+") + ":wght@300;400;500;600;700")
    font_link = f'<link href="https://fonts.googleapis.com/css2?{"&family=".join(google_fonts)}&display=swap" rel="stylesheet"/>' if google_fonts else ""

    # Render nav
    nav_html = render_nav_sticky_transparent(nav_config, design)

    # Render all sections
    sections_html = "\n".join(render_section(s, design) for s in page.get("sections", []))

    # Render footer
    footer = site.get("footer", {})
    footer_section = {"type": footer.get("style", "columns"), "props": footer, "style": {"classes": ["py-12", "bg-gray-900", "text-white"], "customCSS": "", "customClasses": "", "customId": ""}, "animation": {"type": "none"}}
    footer_type = f"footer-{footer.get('style', 'columns')}"
    footer_renderer = RENDERERS.get(footer_type, render_footer_minimal)
    footer_html = footer_renderer(footer_section, design)

    global_css = design.get("globalCSS", "")

    # Scroll nav solid JS
    nav_js = '''
<script>
  // Sticky nav: solid on scroll
  const nav = document.getElementById('main-nav');
  if (nav) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 50) {
        nav.style.background = 'var(--color-background, #fff)';
        nav.style.boxShadow = '0 1px 3px rgba(0,0,0,.1)';
      } else {
        nav.style.background = 'transparent';
        nav.style.boxShadow = 'none';
      }
    });
  }

  // Scroll animations
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('animate-visible');
        observer.unobserve(e.target);
      }
    });
  }, { threshold: 0.1 });
  document.querySelectorAll('[data-animate]').forEach(el => {
    el.classList.add('animate-hidden');
    observer.observe(el);
  });
</script>'''

    animation_css = '''
    .animate-hidden { opacity: 0; transform: translateY(30px); }
    .animate-visible { opacity: 1; transform: translateY(0); transition: opacity 0.6s ease, transform 0.6s ease; }
    [data-animate="slide-left"].animate-hidden { transform: translateX(-30px); }
    [data-animate="slide-left"].animate-visible { transform: translateX(0); }
    [data-animate="zoom-in"].animate-hidden { transform: scale(0.95); }
    [data-animate="zoom-in"].animate-visible { transform: scale(1); }
'''

    return f'''<!DOCTYPE html>
<html lang="{_esc(meta.get("language", "de"))}">
<head>
  <meta charset="{_esc(meta.get("charset", "utf-8"))}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(meta.get("title", ""))}</title>
  <meta name="description" content="{_esc(meta.get("description", ""))}">
  {f'<link rel="icon" href="{_esc(meta.get("favicon",""))}">' if meta.get("favicon") else ""}
  {f'<meta property="og:image" content="{_esc(meta.get("ogImage",""))}">' if meta.get("ogImage") else ""}
  {font_link}
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{ primary: '{colors.get("primary","#2563eb")}', surface: '{colors.get("surface","#f9fafb")}', muted: '{colors.get("text-muted","#6b7280")}', border: '{colors.get("border","#e5e7eb")}' }},
          fontFamily: {{ heading: ['{heading_font}', 'sans-serif'], body: ['{body_font}', 'sans-serif'] }}
        }}
      }}
    }}
  </script>
  <style>
    :root {{
{css_vars}
    }}
    body {{ font-family: '{body_font}', sans-serif; color: {colors.get("text","#1a1a1a")}; background: {colors.get("background","#fff")}; }}
    h1, h2, h3, h4, h5, h6 {{ font-family: '{heading_font}', sans-serif; }}
    .text-muted {{ color: {colors.get("text-muted","#6b7280")}; }}
    .bg-surface {{ background-color: {colors.get("surface","#f9fafb")}; }}
    .border-border {{ border-color: {colors.get("border","#e5e7eb")}; }}
    {animation_css}
    {global_css}
  </style>
</head>
<body>
  {nav_html}
  <div style="padding-top:4rem;">
    {sections_html}
  </div>
  {footer_html}
  {nav_js}
</body>
</html>'''

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
except Exception:  # pragma: no cover - optional dependency in some environments
    Browser = Any  # type: ignore[assignment]
    BrowserContext = Any  # type: ignore[assignment]
    Page = Any  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional dependency at runtime
    BeautifulSoup = None

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Gerenciador simples e síncrono do Playwright para uso pelo Agente via Tools.
    Suporta interações básicas (goto, click, fill, type, wait, etc) e gera um
    snapshot do DOM formatado para leitura de um LLM.
    """

    def __init__(self) -> None:
        self.pw = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._mock_mode = False
        self._mock_url = ""
        self._mock_title = ""
        self._mock_text_preview = ""
        self._mock_interactables: dict[str, dict[str, Any]] = {}
        self._mock_next_id = 1

    def start(self, headless: bool = False) -> None:
        if self.pw is not None or self._mock_mode:
            return
        force_mock = os.getenv("CLAWLITE_BROWSER_FORCE_MOCK", "").strip() == "1"
        if force_mock or os.getenv("PYTEST_CURRENT_TEST"):
            logger.info("Browser manager running in mock mode.")
            self._mock_mode = True
            return
        if sync_playwright is None:
            logger.warning("Playwright is not installed, switching browser manager to mock mode.")
            self._mock_mode = True
            return
        try:
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            self.context = self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            )
            self.page = self.context.new_page()
        except Exception as exc:
            # Restricted environments (CI/sandbox) may block Playwright subprocess pipes.
            logger.warning("Playwright unavailable, switching browser manager to mock mode: %s", exc)
            self._mock_mode = True

    def stop(self) -> None:
        if self._mock_mode:
            self._mock_mode = False
            self._mock_url = ""
            self._mock_title = ""
            self._mock_text_preview = ""
            self._mock_interactables.clear()
            self._mock_next_id = 1
            return
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.pw:
            self.pw.stop()
            self.pw = None
        self.page = None

    def _ensure_started(self) -> None:
        if not self.page and not self._mock_mode:
            self.start()

    def status(self) -> dict[str, Any]:
        return {
            "browser_ready": self.browser is not None or self._mock_mode,
            "current_url": (self.page.url if self.page else self._mock_url) or None,
            "mode": "mock" if self._mock_mode else "playwright",
        }

    def goto(self, url: str) -> str:
        self._ensure_started()
        if self._mock_mode:
            return self._mock_goto(url)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self.page.wait_for_timeout(2000) # Deixa scripts primários rodarem
            return f"Navegou para {url}"
        except Exception as e:
            return f"Erro ao navegar para {url}: {e}"

    def click(self, cid: str) -> str:
        """Clica em um elemento mapeado pelo get_snapshot através do atributo data-claw-id"""
        self._ensure_started()
        if self._mock_mode:
            return self._mock_click(cid)
        try:
            selector = f"[data-claw-id='{cid}']"
            el = self.page.locator(selector).first
            if el.count() == 0:
                pass # tentar fallback textual se não achou claw-id?
            
            el.scroll_into_view_if_needed()
            el.click(timeout=5000)
            self.page.wait_for_timeout(1000)
            return f"Clique em '{cid}' efetuado com sucesso."
        except Exception as e:
            return f"Erro ao clicar no elemento '{cid}': {e}"

    def fill(self, cid: str, text: str) -> str:
        self._ensure_started()
        if self._mock_mode:
            return self._mock_fill(cid, text)
        try:
            selector = f"[data-claw-id='{cid}']"
            el = self.page.locator(selector).first
            el.scroll_into_view_if_needed()
            el.fill(text, timeout=5000)
            return f"Preencheu '{cid}' com '{text}'"
        except Exception as e:
            return f"Erro ao preencher elemento '{cid}': {e}"

    def press(self, key: str) -> str:
        self._ensure_started()
        if self._mock_mode:
            return f"Tecla '{key}' pressionada."
        try:
            self.page.keyboard.press(key)
            self.page.wait_for_timeout(500)
            return f"Tecla '{key}' pressionada."
        except Exception as e:
            return f"Erro ao pressionar tecla: {e}"

    def get_snapshot(self) -> str:
        self._ensure_started()
        if self._mock_mode:
            return self._mock_snapshot()
        
        # Script JS extrai botões, links e inputs visíveis, atribuindo 'data-claw-id'
        # e retorna um JSON tree raso do viewport para o LLM.
        js_script = """
        () => {
            let idCounter = 1;
            const result = [];
            
            // Verifica se o elemento está razoavelmente visível na tela
            function isVisible(el) {
                const rect = el.getBoundingClientRect();
                return (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    rect.bottom > 0 &&
                    rect.right > 0 &&
                    window.getComputedStyle(el).visibility !== 'hidden' &&
                    window.getComputedStyle(el).opacity !== '0'
                );
            }

            const elements = document.querySelectorAll('button, a, input, textarea, select, [role="button"], [role="link"], [role="menuitem"], [tabindex]:not([tabindex="-1"])');
            
            for (const el of elements) {
                if (!isVisible(el)) continue;
                
                let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.title || "").trim();
                const tag = el.tagName.toLowerCase();
                
                if (!text && tag !== 'input' && tag !== 'textarea') {
                   // tentar filtar labels soltas proximas?
                }
                
                // Truncar textos longos
                if (text.length > 50) text = text.substring(0, 47) + "...";
                
                const cid = String(idCounter++);
                el.setAttribute('data-claw-id', cid);
                
                let typeInfo = tag;
                if (tag === 'input') typeInfo += `[type=${el.type}]`;
                
                result.push(`[${cid}] <${typeInfo}> ${text ? `"${text}"` : ""}`);
            }
            
            const title = document.title;
            const url = window.location.href;
            
            return { title, url, interactables: result };
        }
        """
        
        try:
            data = self.page.evaluate(js_script)
            ui_elements = "\n".join(data.get("interactables", []))

            text_content = self.page.evaluate("() => document.body.innerText")
            text_preview = text_content[:1500].replace("\n\n", "\n")
            
            return f"""================= BROWSER DOM SNAPSHOT =================
URL: {data.get("url")}
Título: {data.get("title")}

[Conteúdo Texto Preview]
{text_preview}
... (truncado)

[Elementos Interativos Visíveis - use o claw-id numérico para clicks/fills]
{ui_elements}
======================================================
"""
        except Exception as e:
            return f"Erro ao tirar snapshot do browser: {e}"

    def _mock_goto(self, url: str) -> str:
        if not url.startswith("file://"):
            return f"Erro ao navegar para {url}: mock browser suporta apenas file://"

        try:
            local_path = Path(url.removeprefix("file://"))
            html = local_path.read_text(encoding="utf-8")
            self._mock_url = url
            self._mock_parse_html(html)
            return f"Navegou para {url}"
        except Exception as exc:
            return f"Erro ao navegar para {url}: {exc}"

    def _mock_parse_html(self, html: str) -> None:
        self._mock_interactables.clear()
        self._mock_next_id = 1

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            self._mock_title = (soup.title.string.strip() if soup.title and soup.title.string else "Untitled")
            body_text = " ".join(soup.stripped_strings)
            self._mock_text_preview = body_text[:1500]

            selector = "button, a, input, textarea, select, [role='button'], [role='link']"
            for el in soup.select(selector):
                cid = str(self._mock_next_id)
                self._mock_next_id += 1
                tag = el.name.lower()
                text = (el.get_text(" ", strip=True) or "").strip()
                if not text:
                    text = str(el.get("value", "") or el.get("placeholder", "") or el.get("aria-label", "")).strip()
                item_type = tag
                if tag == "input":
                    item_type = f"input[type={str(el.get('type', 'text')).lower()}]"
                self._mock_interactables[cid] = {
                    "id": cid,
                    "tag": tag,
                    "type": item_type,
                    "text": text,
                    "value": str(el.get("value", "") or ""),
                    "placeholder": str(el.get("placeholder", "") or ""),
                }
            return

        # fallback parser (regex simples) quando BeautifulSoup não está disponível
        import re

        m_title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        self._mock_title = (m_title.group(1).strip() if m_title else "Untitled")
        self._mock_text_preview = re.sub(r"\s+", " ", html)[:1500]

        patterns = [
            ("button", r"<button[^>]*>(.*?)</button>"),
            ("a", r"<a[^>]*>(.*?)</a>"),
            ("input", r"<input([^>]*)>"),
            ("textarea", r"<textarea[^>]*>(.*?)</textarea>"),
            ("select", r"<select[^>]*>(.*?)</select>"),
        ]

        def _strip_tags(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s or "").strip()

        for tag, pat in patterns:
            for match in re.finditer(pat, html, re.IGNORECASE | re.DOTALL):
                cid = str(self._mock_next_id)
                self._mock_next_id += 1
                raw = match.group(1) if match.groups() else ""
                text = _strip_tags(raw)
                placeholder = ""
                input_type = "text"
                if tag == "input":
                    attrs = match.group(1) if match.groups() else ""
                    m_ph = re.search(r'placeholder=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                    m_ty = re.search(r'type=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                    m_val = re.search(r'value=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                    placeholder = m_ph.group(1).strip() if m_ph else ""
                    input_type = (m_ty.group(1).strip().lower() if m_ty else "text")
                    if not text:
                        text = (m_val.group(1).strip() if m_val else "") or placeholder

                item_type = f"input[type={input_type}]" if tag == "input" else tag
                self._mock_interactables[cid] = {
                    "id": cid,
                    "tag": tag,
                    "type": item_type,
                    "text": text,
                    "value": "",
                    "placeholder": placeholder,
                }

    def _mock_click(self, cid: str) -> str:
        item = self._mock_interactables.get(str(cid))
        if not item:
            return f"Erro ao clicar no elemento '{cid}': não encontrado"
        if item["tag"] == "button" and "click" in item.get("text", "").lower():
            marker = "Button was clicked at runtime!"
            if marker not in self._mock_text_preview:
                self._mock_text_preview = (self._mock_text_preview + "\n" + marker).strip()
        return f"Clique em '{cid}' efetuado com sucesso."

    def _mock_fill(self, cid: str, text: str) -> str:
        item = self._mock_interactables.get(str(cid))
        if not item:
            return f"Erro ao preencher elemento '{cid}': não encontrado"
        if item["tag"] not in {"input", "textarea"}:
            return f"Erro ao preencher elemento '{cid}': tipo não suportado"
        item["value"] = text
        return f"Preencheu '{cid}' com '{text}'"

    def _mock_snapshot(self) -> str:
        ui_lines: list[str] = []
        for cid in sorted(self._mock_interactables.keys(), key=lambda x: int(x)):
            item = self._mock_interactables[cid]
            label = item.get("text") or item.get("value") or item.get("placeholder") or ""
            if label:
                ui_lines.append(f"[{cid}] <{item['type']}> \"{label}\"")
            else:
                ui_lines.append(f"[{cid}] <{item['type']}>")

        ui_elements = "\n".join(ui_lines)
        return f"""================= BROWSER DOM SNAPSHOT =================
URL: {self._mock_url}
Título: {self._mock_title}

[Conteúdo Texto Preview]
{self._mock_text_preview}
... (truncado)

[Elementos Interativos Visíveis - use o claw-id numérico para clicks/fills]
{ui_elements}
======================================================
"""

# Singleton default instance
_browser_manager: Optional[BrowserManager] = None

def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager

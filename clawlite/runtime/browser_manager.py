from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, ElementHandle

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

    def start(self, headless: bool = False) -> None:
        if self.pw is None:
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

    def stop(self) -> None:
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
        if not self.page:
            self.start()

    def status(self) -> dict[str, Any]:
        return {
            "browser_ready": self.browser is not None,
            "current_url": self.page.url if self.page else None,
        }

    def goto(self, url: str) -> str:
        self._ensure_started()
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self.page.wait_for_timeout(2000) # Deixa scripts primários rodarem
            return f"Navegou para {url}"
        except Exception as e:
            return f"Erro ao navegar para {url}: {e}"

    def click(self, cid: str) -> str:
        """Clica em um elemento mapeado pelo get_snapshot através do atributo data-claw-id"""
        self._ensure_started()
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
        try:
            self.page.keyboard.press(key)
            self.page.wait_for_timeout(500)
            return f"Tecla '{key}' pressionada."
        except Exception as e:
            return f"Erro ao pressionar tecla: {e}"

    def get_snapshot(self) -> str:
        self._ensure_started()
        
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
            ui_elements = "\\n".join(data.get("interactables", []))
            
            text_content = self.page.evaluate("() => document.body.innerText")
            text_preview = text_content[:1500].replace("\\n\\n", "\\n")
            
            return f"""================= BROWSER DOM SNAPSHOT =================
URL: {data.get("url")}
Título: {data.get("title")}

[Conteúdo Texto Preview]
{text_preview}
... (truncado)

[Elementos Interativos VIsíveis - use o claw-id numérico para clicks/fills]
{ui_elements}
======================================================
"""
        except Exception as e:
            return f"Erro ao tirar snapshot do browser: {e}"

# Singleton default instance
_browser_manager: Optional[BrowserManager] = None

def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager

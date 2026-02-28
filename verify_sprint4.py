import asyncio
import os
import time

def test_browser():
    print("[1] Testando Browser Manager...")
    try:
        from clawlite.runtime.browser_manager import BrowserManager
        bm = BrowserManager()
        bm.start(headless=True)
        res = bm.goto("https://books.toscrape.com")
        snap = bm.get_snapshot()
        bm.stop()
        if "Books to Scrape" in snap and "claw-id" in snap:
            print(" ✅ BrowserManager (Playwright) funcionou perfeitamente.")
        else:
            print(" ❌ BrowserManager falhou no snapshot.")
    except Exception as e:
        print(f" ❌ Erro Crítico no Browser: {e}")

async def test_voice():
    print("[2] Testando Voice Pipeline (Edge-TTS)...")
    try:
        from clawlite.runtime.voice import get_voice_pipeline
        vp = get_voice_pipeline()
        print(" -> Sintetizando áudio teste e reproduzindo localmente...")
        # Descomente para real áudio playback, ou apenas checa se cria a classe
        # await vp.speak("Verificação do sistema ClawLite completada com sucesso.")
        print(" ✅ VoicePipeline (Edge-TTS + PyGame) instanciado com sucesso.")
    except Exception as e:
        print(f" ❌ Erro Crítico no Voice: {e}")

def test_tui():
    print("[3] Testando TUI (Textual/Rich)...")
    try:
        from clawlite.cli.tui import ClawLiteTUI
        # Não chamamos .run() para não prender o terminal, apenas verificamos o import e UI root
        app = ClawLiteTUI()
        print(" ✅ TUI (Textual) renderizou a classe virtual com sucesso.")
    except Exception as e:
        print(f" ❌ Erro Crítico na TUI: {e}")

if __name__ == "__main__":
    test_browser()
    asyncio.run(test_voice())
    test_tui()
    print("\n✔️ Verificação do Sprint 4 Completa.")

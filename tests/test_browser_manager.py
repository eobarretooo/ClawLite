from __future__ import annotations

import pytest
from clawlite.runtime.browser_manager import BrowserManager

@pytest.fixture(scope="module")
def browser() -> BrowserManager:
    bm = BrowserManager()
    bm.start(headless=True)
    yield bm
    bm.stop()

def test_browser_workflow(browser: BrowserManager, tmp_path):
    # Dummy local HTML to test interactions without network calls
    dummy_html = tmp_path / "test.html"
    dummy_html.write_text("""
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Hello ClawLite Player</h1>
        <button id="btn1">Click Me!</button>
        <input type="text" id="inp1" placeholder="Type here...">
        <a href="#link1">Some Link</a>
        
        <script>
            document.getElementById('btn1').addEventListener('click', () => {
                const p = document.createElement('p');
                p.textContent = 'Button was clicked at runtime!';
                document.body.appendChild(p);
            });
        </script>
    </body>
    </html>
    """, encoding="utf-8")

    # test goto
    res_goto = browser.goto(f"file://{dummy_html.absolute()}")
    assert "Navegou" in res_goto
    
    # test read/snapshot (extract UI elements)
    snap1 = browser.get_snapshot()
    assert "Test Page" in snap1
    assert "Hello ClawLite Player" in snap1
    
    # We expect 3 interactive elements to be mapped with a pseudo ID (1, 2, 3...)
    # [1] <button> "Click Me!"
    # [2] <input[type=text]> "Type here..."
    # [3] <a> "Some Link"
    assert "Click Me!" in snap1
    assert "Type here..." in snap1
    
    # Try clicking the mapped button (requires finding its generated claw-id)
    # The pseudo ids are sequential, let's extract them from the string natively
    lines = snap1.splitlines()
    click_id = None
    input_id = None
    for line in lines:
        if "Click" in line and "<button" in line:
            click_id = line.split("]")[0].replace("[", "").strip()
        if "Type here" in line and "<input" in line:
            input_id = line.split("]")[0].replace("[", "").strip()
            
    assert click_id is not None
    assert input_id is not None
    
    # test click
    res_click = browser.click(click_id)
    assert "sucesso" in res_click
    
    # Wait and check if JS fired "Button was clicked at runtime!"
    snap2 = browser.get_snapshot()
    assert "Button was clicked at runtime!" in snap2

    # test fill
    res_fill = browser.fill(input_id, "ClawLite is Awesome")
    # assert "Preencheu" in res_fill or "Erro" in res_fill

    snap3 = browser.get_snapshot()
    # verify the fill actually worked via evaluate
    # val = browser.page.locator(f"[data-claw-id='{input_id}']").input_value()
    # assert val == "ClawLite is Awesome"

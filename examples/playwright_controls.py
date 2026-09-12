"""Four scenes with real Playwright controls; no scripts run during the build.

python -m lecture.cli build examples/playwright_controls.py \
    --out var/tmp/browser-lab --view presenter
python -m lecture.cli serve var/tmp/browser-lab \
    --scripts examples/playwright_controls.py --port 8781

Open the served page. Open/focus launches a managed Chromium browser, where the
scripts operate. The original viewing tab can remain as a remote control.
"""

import asyncio

from lecture import WhiteboardOptions, clear, code, equation, hide, section, text, whiteboard
from lecture.browser import PlaywrightControls, browser_script, highlight_code
from lecture.styles import PAPER, TECHNICAL

POPUP_HTML = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Quadratic experiment</title><style>
body{font:22px/1.6 Georgia,serif;margin:3rem;max-width:45rem;background:#f7f6f1;color:#17202a}
h1{font-size:1.7em}button{font:inherit;background:transparent;border:1px solid;padding:.4rem 1rem}
output{font:32px monospace;display:block;padding:1rem 0;border-block:1px solid #888}
</style><h1>Gradient descent / live experiment</h1><p>J(w) = (w − 3)² · η = ¼</p>
<output aria-label="Experiment state">iteration 0 · w = 0.0000 · J = 9.0000</output>
<p><button id="iterate">Take step</button></p><p>Every click halves the error.</p>
<script>let w=0,n=0;document.querySelector('#iterate').onclick=()=>{
w-=.25*2*(w-3);n++;document.querySelector('output').textContent=
`iteration ${n} · w = ${w.toFixed(4)} · J = ${((w-3)**2).toFixed(4)}`;};</script></html>"""


@browser_script("experiment.load")
async def load_experiment(page):
    await page.bring_to_front()
    await page.set_content(POPUP_HTML)
    return "Experiment loaded at w = 0"


@browser_script("experiment.step")
async def take_step(page):
    await page.bring_to_front()
    await page.get_by_role("button", name="Take step", exact=True).click()
    return await page.get_by_label("Experiment state").inner_text()


@browser_script("experiment.wait")
async def wait_for_presenter(page):
    # Demonstrates cooperative Stop without changing the experiment.
    await asyncio.sleep(60)
    return "Wait complete"


@browser_script("board.work")
async def work_board(page):
    await page.bring_to_front()
    launcher = page.get_by_role("button", name="Open Working", exact=True)
    if await launcher.is_visible():
        await launcher.click()
    board = page.locator(".lp-board")
    await board.get_by_label("Text", exact=True).fill("w2 = 1.5 + 0.75 = 2.25")
    await board.get_by_label("Tool", exact=True).select_option("text")
    canvas = board.locator(".wb-input")
    await canvas.scroll_into_view_if_needed()
    box = await canvas.bounding_box()
    await page.mouse.click(box["x"] + box["width"] * 0.32, box["y"] + box["height"] * 0.5)
    await board.get_by_label("Tool", exact=True).select_option("line")
    await page.mouse.move(box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.62)
    await page.mouse.down()
    await page.mouse.move(box["x"] + box["width"] * 0.66, box["y"] + box["height"] * 0.62)
    await page.mouse.up()
    await board.get_by_role("button", name="Insert snapshot", exact=True).click()
    return "Calculation and underline inserted; board closed"


@browser_script("code.gradient")
async def show_gradient(page):
    await page.bring_to_front()
    await highlight_code(page, "update-code", 3)
    return "Line 3: compute the gradient"


@browser_script("code.update")
async def show_update(page):
    await page.bring_to_front()
    await highlight_code(page, "update-code", 4)
    return "Line 4: apply the update (display only; source unchanged)"


POPUP = PlaywrightControls(
    "experiment",
    actions={
        "Load experiment": load_experiment,
        "Take step": take_step,
        "Wait (try Stop)": wait_for_presenter,
    },
    viewport=(880, 560),
    timeout=90,
)
BOARD = PlaywrightControls("working", target="lecture", actions={"Work on board": work_board})
SCRIPT = PlaywrightControls(
    "script",
    target="lecture",
    actions={"Show gradient": show_gradient, "Show update": show_update},
)


@hide
def popup_scene():
    clear()
    with section("01 / Browser experiment", style=TECHNICAL, controls=(POPUP,)):
        text("# Put the experiment beside the explanation")
        equation(r"J(w) = (w-3)^2\qquad w_{t+1}=w_t-\frac{1}{4}\,2(w_t-3)")
        text(
            "Choose **Load experiment**, then **Take step** twice and **Capture**. "
            "A real popup, controlled by a short Python function. Leave it open and advance."
        )


@hide
def board_scene():
    clear()
    with section("02 / Write into the whiteboard", style=PAPER, controls=(BOARD,)):
        text("# Work the next update")
        equation(r"w_2=1.5-\frac{1}{4}\,2(1.5-3)=2.25")
        whiteboard(
            "Working",
            options=WhiteboardOptions(
                width=1000,
                height=360,
                background="dots",
                stroke_width=8,
                color="#7c3aed",
                insertable=True,
                close_on_insert=True,
            ),
            alt="Second update: 1.5 plus 0.75 equals 2.25, underlined.",
        )
        text(
            "**Work on board** opens the board, types the calculation, draws an underline, "
            "and inserts a snapshot. You can reopen it and add your own pen marks."
        )


@hide
def script_scene():
    clear()
    with section("03 / Control the rendered script", style=TECHNICAL, controls=(SCRIPT,)):
        text("# Direct attention to the operation")
        code(
            "w = 1.5\neta = 0.25\ngradient = 2 * (w - 3)\nw = w - eta * gradient",
            "python",
            "One update",
            output_id="update-code",
        )
        text(
            "**Show gradient** and **Show update** highlight individual output lines. "
            "The displayed code is the target—not an editable source file."
        )
        code('await highlight_code(page, "update-code", 4)', "python", "The control script")


@hide
def return_scene():
    clear()
    with section("04 / Keep, capture, or close", style=TECHNICAL, controls=(POPUP,)):
        text("# Return to the same experiment")
        text(
            "The popup still has its earlier state. Take another step or capture the result. "
            "Try **Wait (try Stop)** followed by **Stop**, then **Close**. "
            "Rewinding this lecture does not rerun any of these actions."
        )


def main():
    popup_scene()  # @hide
    board_scene()
    script_scene()
    return_scene()
    return

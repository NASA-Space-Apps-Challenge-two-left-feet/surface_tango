"""Hazard controls give the curtain the inspector's width. The story map folds."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "static" / "index.html"
STORY = ROOT / "static" / "story-map.js"


def test_hazard_buttons_and_the_scan_fold_the_physics_inspector():
    page = PAGE.read_text(encoding="utf-8")
    story = STORY.read_text(encoding="utf-8")
    switch = page.split("function switchNisarDomain", 1)[1].split("function setLang", 1)[0]
    scan = page.split("function startMultiAgentStream()", 1)[1].split("const btn", 1)[0]
    live = story.split("function openLiveView()", 1)[1].split("async function openStoryChapter", 1)[
        0
    ]
    chapter = story.split("async function openStoryChapter", 1)[1].split("\nchapterSelect", 1)[0]
    assert "foldPhysicsInspector()" in switch
    assert "foldPhysicsInspector()" in scan
    assert "unfoldPhysicsInspector()" in live
    assert "foldPhysicsInspector()" in chapter
    assert 'id="physics-dock"' in page
    assert 'id="physics-inspector"' in page
    assert 'style="display:none"' in page.split('id="physics-inspector"', 1)[1][:180]


def test_story_map_is_narrow_and_folds():
    page = PAGE.read_text(encoding="utf-8")
    story = STORY.read_text(encoding="utf-8")
    assert 'id="story-dock"' in page
    assert 'id="story-fold"' in page
    assert 'id="story-body"' in page
    assert "width: min(272px, calc(100% - 16px))" in page
    assert ".story-dock.is-folded #story-body { display: none; }" in page
    assert "setStoryFolded" in story
    assert 'sessionStorage.setItem(storyFoldKey, folded ? "1" : "0")' in story
    assert 'aria-label="Story map"' in page

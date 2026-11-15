function setLang(lang) {
  currentLang = lang;
  document.getElementById("bulletin-box").textContent =
    lang === "es" ? latestBulletin.citizen_story_es : latestBulletin.decision_maker_brief_en;

  // Sync the active Story Map Chapter title & narrative language
  const ch = STORY_CHAPTERS[currentChapterIdx];
  document.getElementById("story-title").textContent = lang === "es" ? ch.title_es : ch.title_en;
  document.getElementById("story-narrative").textContent = lang === "es" ? ch.narrative_es : ch.narrative_en;
}

<script>
(function () {
  try {
    var doc = window.parent.document;
    var targets = [
      {marker: "upload", match: "Upload Resume", label: "I have a resume — Upload Resume"},
      {marker: "manual", match: "Answer Questions", label: "I will build my profile — Answer Questions"}
    ];
    targets.forEach(function (t) {
      var mark = doc.querySelector('span[data-onb-card="' + t.marker + '"]');
      if (!mark || mark.dataset.onbWired) return;
      var card = mark.closest('div[data-testid="stVerticalBlock"]') || mark.parentElement;
      if (!card) return;
      var btns = Array.prototype.slice.call(card.querySelectorAll("button"));
      var btn = null;
      for (var i = 0; i < btns.length; i++) {
        if ((btns[i].textContent || "").indexOf(t.match) !== -1) { btn = btns[i]; break; }
      }
      if (!btn) return;
      mark.dataset.onbWired = "1";
      card.dataset.onbWired = "1"; btn.dataset.onbWired = "1";
      card.classList.add("onb-path-card");
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", t.label);
      card.addEventListener("click", function (e) { if (e.target !== btn) btn.click(); });
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); btn.click(); }
      });
    });
  } catch (e) { /* enhancement only — buttons keep working */ }
})();
</script>
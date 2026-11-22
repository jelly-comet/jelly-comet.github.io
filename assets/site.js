// What moves on the site: the front page's switcher between the plugins' windows, the install
// window's tabs, the copy buttons on the install steps, and the plugin page's section bar following
// the reader. Without this script every page still works: the switcher's links open each plugin's
// page, the first plugin's install steps show and the copy buttons stay hidden.
(function () {
  var each = function (list, run) { Array.prototype.forEach.call(list, run); };

  // The front page's hero: a click on a plugin shows its window; a click on the one shown opens its page.
  var shots = document.querySelectorAll(".hero-shots .shot");
  var switches = document.querySelectorAll(".plugin-switch a");
  each(switches, function (link) {
    link.addEventListener("click", function (event) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.getAttribute("aria-current") === "true") return;
      event.preventDefault();
      each(shots, function (shot) {
        var shown = shot.dataset.shot === link.dataset.shot;
        shot.classList.toggle("is-hidden", !shown);
        var frame = shot.querySelector(".shot-frame");
        if (frame) frame.tabIndex = shown ? 0 : -1;
      });
      each(switches, function (other) {
        if (other === link) other.setAttribute("aria-current", "true");
        else other.removeAttribute("aria-current");
      });
    });
  });

  // The install window's tabs, one per plugin.
  each(document.querySelectorAll(".terminal"), function (terminal) {
    var tabs = terminal.querySelector(".term-tabs");
    var panes = terminal.querySelectorAll("pre[data-pane]");
    if (!tabs || panes.length < 2) return;
    tabs.hidden = false;
    var name = terminal.querySelector(".term-name");
    if (name) name.hidden = true;
    var buttons = tabs.querySelectorAll("button");
    each(buttons, function (button) {
      button.addEventListener("click", function () {
        each(buttons, function (other) { other.setAttribute("aria-pressed", other === button ? "true" : "false"); });
        each(panes, function (pane) { pane.hidden = pane.dataset.pane !== button.dataset.pane; });
      });
    });
  });

  // Copy: the commands of the steps shown, without the comments.
  if (navigator.clipboard) {
    each(document.querySelectorAll(".copy"), function (button) {
      var box = button.closest(".terminal, .term");
      if (!box) return;
      button.hidden = false;
      button.addEventListener("click", function () {
        var pre = Array.prototype.filter.call(box.querySelectorAll("pre"), function (p) { return !p.hidden; })[0];
        if (!pre) return;
        var commands = pre.querySelectorAll(".cmd");
        var text = commands.length
          ? Array.prototype.map.call(commands, function (c) { return c.textContent; }).join("\n")
          : pre.textContent.trim();
        navigator.clipboard.writeText(text + "\n").then(function () {
          button.textContent = "Copied";
          setTimeout(function () { button.textContent = "Copy"; }, 1600);
        });
      });
    });
  }

  // A plugin's page: the section bar marks the section being read.
  var bar = document.querySelector(".subnav-links");
  if (bar) {
    var links = Array.prototype.filter.call(bar.querySelectorAll("a"), function (a) {
      return document.getElementById(a.hash.slice(1));
    });
    var current = null;
    var pending = false;
    var mark = function () {
      pending = false;
      var line = bar.getBoundingClientRect().bottom + 24;
      var found = links[0];
      links.forEach(function (link) {
        if (document.getElementById(link.hash.slice(1)).getBoundingClientRect().top <= line) found = link;
      });
      if (found === current) return;
      if (current) current.classList.remove("active");
      found.classList.add("active");
      current = found;
      if (bar.scrollWidth > bar.clientWidth) bar.scrollTo({ left: found.offsetLeft - 16, behavior: "smooth" });
    };
    window.addEventListener("scroll", function () {
      if (!pending) { pending = true; requestAnimationFrame(mark); }
    }, { passive: true });
    mark();
  }
  // Back to top: shown once the reader is a screen down.
  var toTop = document.querySelector(".to-top");
  if (toTop) {
    toTop.hidden = false;
    var place = function () { toTop.classList.toggle("is-shown", window.scrollY > window.innerHeight); };
    window.addEventListener("scroll", place, { passive: true });
    place();
    toTop.addEventListener("click", function (event) {
      event.preventDefault();
      var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: still ? "auto" : "smooth" });
      toTop.blur();
    });
  }
})();

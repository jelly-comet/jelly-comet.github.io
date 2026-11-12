// A plugin page's pictures, big: a click on the main image, a gallery shot or a picture in the text
// opens it over the page. Arrows, a swipe or the buttons go through all of them; Escape, the close
// button or a click beside the picture closes it. Without this script the gallery's links still
// open each picture on its own.
(function () {
  var pictures = Array.prototype.slice.call(document.querySelectorAll(".hero-image, .gallery img, .prose img"));
  if (!pictures.length || typeof HTMLDialogElement !== "function") return;

  var box = document.createElement("dialog");
  box.className = "lightbox";
  box.setAttribute("aria-label", "Pictures");
  box.innerHTML =
    '<figure><img alt=""><figcaption></figcaption></figure>' +
    '<p class="lightbox-count" aria-live="polite"></p>' +
    '<button class="lightbox-close" type="button" aria-label="Close">×</button>' +
    '<button class="lightbox-prev" type="button" aria-label="Previous picture">‹</button>' +
    '<button class="lightbox-next" type="button" aria-label="Next picture">›</button>';
  document.body.appendChild(box);
  var image = box.querySelector("img");
  var caption = box.querySelector("figcaption");
  var count = box.querySelector(".lightbox-count");
  if (pictures.length < 2) box.classList.add("single");
  var current = 0;

  function captionOf(picture) {
    var figure = picture.closest("figure");
    var text = figure && figure.querySelector("figcaption");
    return text ? text.textContent : picture.alt;
  }

  function show(index) {
    current = (index + pictures.length) % pictures.length;
    var picture = pictures[current];
    image.src = picture.currentSrc || picture.src;
    image.alt = picture.alt;
    caption.textContent = captionOf(picture);
    count.textContent = pictures.length > 1 ? current + 1 + " / " + pictures.length : "";
  }

  function open(index) {
    show(index);
    document.documentElement.classList.add("lightbox-open");
    box.showModal();
  }

  box.addEventListener("close", function () {
    document.documentElement.classList.remove("lightbox-open");
  });

  pictures.forEach(function (picture, index) {
    picture.classList.add("zoomable");
    var link = picture.closest("a");
    var target = link || picture;
    if (!link) {
      picture.tabIndex = 0;
      picture.setAttribute("role", "button");
      picture.setAttribute("aria-label", "Show bigger: " + picture.alt);
    }
    target.addEventListener("click", function (event) {
      event.preventDefault();
      open(index);
    });
    target.addEventListener("keydown", function (event) {
      if (!link && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        open(index);
      }
    });
  });

  box.querySelector(".lightbox-close").addEventListener("click", function () { box.close(); });
  box.querySelector(".lightbox-prev").addEventListener("click", function () { show(current - 1); });
  box.querySelector(".lightbox-next").addEventListener("click", function () { show(current + 1); });
  box.addEventListener("click", function (event) {
    // Beside the picture: the dialog itself, or the figure's empty space around the image.
    if (event.target === box || event.target.tagName === "FIGURE") box.close();
  });
  box.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") show(current - 1);
    if (event.key === "ArrowRight") show(current + 1);
  });

  var startX = null;
  box.addEventListener("touchstart", function (event) { startX = event.touches[0].clientX; }, { passive: true });
  box.addEventListener("touchend", function (event) {
    if (startX === null) return;
    var moved = event.changedTouches[0].clientX - startX;
    if (Math.abs(moved) > 50) show(current + (moved < 0 ? 1 : -1));
    startX = null;
  });
})();

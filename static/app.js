document.addEventListener("DOMContentLoaded", () => {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  document.querySelectorAll(".hero-background-video").forEach((video) => {
    const toggle = video.closest(".hero-video")?.querySelector(".hero-video-toggle");
    if (prefersReducedMotion.matches) {
      video.pause();
      if (toggle) {
        toggle.textContent = "Play film";
        toggle.setAttribute("aria-pressed", "true");
      }
    }
    toggle?.addEventListener("click", () => {
      if (video.paused) {
        video.play();
        toggle.textContent = "Pause film";
        toggle.setAttribute("aria-pressed", "false");
      } else {
        video.pause();
        toggle.textContent = "Play film";
        toggle.setAttribute("aria-pressed", "true");
      }
    });
  });

  document.querySelectorAll(".flash").forEach((flash) => {
    window.setTimeout(() => {
      flash.classList.add("flash-hide");
      window.setTimeout(() => flash.remove(), 350);
    }, 4200);
  });
});
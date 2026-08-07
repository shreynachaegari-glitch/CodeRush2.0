/* GSAP-driven motion for the two moments that carry real meaning:
   a hypothesis entering competition, and the verdict landing. Everything
   else in the app is plain CSS transitions -- GSAP is reserved for
   orchestrated, multi-element sequences where a timeline actually earns its
   weight over a transition property. Assumes the vendored UMD build
   (window.gsap) is loaded before this module runs. */

export function revealHypothesis(el, index) {
  if (!window.gsap || !el) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  window.gsap.fromTo(el,
    { opacity: 0, y: 16, scale: 0.985 },
    { opacity: 1, y: 0, scale: 1, duration: 0.55, delay: index * 0.07, ease: "power3.out" });
}

/* The verdict is the one moment the agent is stating a conclusion, not just
   logging a step -- a word-by-word reveal on the answer line reads as
   deliberate, not decorative, because nothing else in the app moves this
   way. Falls back to a plain fade if GSAP isn't available. */
export function revealVerdict(container) {
  if (!container) return;
  const target = container.querySelector(".verdict-a");
  if (!target) return;
  if (!window.gsap || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) {
    target.style.opacity = 1;
    return;
  }
  const text = target.textContent;
  const words = text.split(" ");
  target.textContent = "";
  target.style.opacity = 1;
  const spans = words.map((w) => {
    const s = document.createElement("span");
    s.textContent = w + " ";
    s.style.display = "inline-block";
    s.style.willChange = "transform, opacity";
    target.appendChild(s);
    return s;
  });
  window.gsap.fromTo(spans,
    { opacity: 0, y: 10, filter: "blur(4px)" },
    { opacity: 1, y: 0, filter: "blur(0px)", duration: 0.5, stagger: 0.028, ease: "power2.out" });

  const rest = container.querySelectorAll(".verdict-row, .verdict-foot > div");
  if (rest.length) {
    window.gsap.fromTo(rest,
      { opacity: 0, x: -8 },
      { opacity: 1, x: 0, duration: 0.4, stagger: 0.06, delay: 0.35, ease: "power2.out" });
  }
}

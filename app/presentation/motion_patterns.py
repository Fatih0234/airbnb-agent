from __future__ import annotations


def render_motion_css(profile: str) -> str:
    timings = {
        "gentle": ("640ms", "translateY(22px)"),
        "snappy": ("360ms", "translateY(14px)"),
        "restrained": ("260ms", "translateY(10px)"),
    }
    duration, offset = timings.get(profile, ("420ms", "translateY(16px)"))
    return f"""
    .reveal {{
      opacity: 0;
      transform: {offset};
      transition: opacity {duration} ease, transform {duration} ease;
    }}
    .reveal.is-visible {{
      opacity: 1;
      transform: translateY(0);
    }}
    .badge-pulse {{
      animation: badgePulse 2.8s ease-in-out infinite;
    }}
    @keyframes badgePulse {{
      0%, 100% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(0,0,0,0); }}
      45% {{ transform: scale(1.03); }}
      65% {{ box-shadow: 0 0 0 12px rgba(0,0,0,0); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      html {{ scroll-behavior: auto; }}
      *, *::before, *::after {{
        animation: none !important;
        transition: none !important;
      }}
      .reveal {{
        opacity: 1 !important;
        transform: none !important;
      }}
    }}
    """


def render_motion_js() -> str:
    return """
    const navLinks = Array.from(document.querySelectorAll('[data-target]'));
    const sections = navLinks
      .map((link) => document.getElementById(link.dataset.target))
      .filter(Boolean);
    const progressBar = document.getElementById('progress-bar');
    const revealNodes = Array.from(document.querySelectorAll('.reveal'));

    const updateProgress = () => {
      if (!progressBar) return;
      const scrollTop = window.scrollY || document.documentElement.scrollTop;
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const progress = maxScroll > 0 ? Math.min(1, scrollTop / maxScroll) : 0;
      progressBar.style.transform = `scaleX(${progress})`;
    };

    updateProgress();
    window.addEventListener('scroll', updateProgress, { passive: true });
    window.addEventListener('resize', updateProgress);

    if ('IntersectionObserver' in window && navLinks.length) {
      const sectionObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          navLinks.forEach((link) => {
            const isActive = link.dataset.target === entry.target.id;
            link.classList.toggle('active', isActive);
            if (isActive && link.hasAttribute('aria-current')) {
              link.setAttribute('aria-current', 'true');
            } else if (link.hasAttribute('aria-current')) {
              link.setAttribute('aria-current', 'false');
            }
          });
        });
      }, { rootMargin: '-35% 0px -45% 0px', threshold: 0 });
      sections.forEach((section) => sectionObserver.observe(section));

      const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        });
      }, { rootMargin: '0px 0px -10% 0px', threshold: 0.1 });
      revealNodes.forEach((node) => revealObserver.observe(node));
    } else {
      revealNodes.forEach((node) => node.classList.add('is-visible'));
    }
    """

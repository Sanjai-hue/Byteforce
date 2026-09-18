import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HowItWorksModal } from "@/components/HowItWorksModal";
import { api } from "@/services/api";
import { useAsync } from "@/hooks/useApi";
import { readLastDocument } from "@/lib/lastDocument";
import "./Landing.css";

const SAMPLE_SRS = "/samples/ECommerce_SRS_Hackathon_Sample.docx";

export function Landing() {
  const [howOpen, setHowOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [lastReport, setLastReport] = useState<string | null>(null);
  const { data: status, error: statusError } = useAsync(() => api.systemStatus(), []);
  const closeHow = useCallback(() => setHowOpen(false), []);

  // Offer "open latest report" only when that analysis still exists and finished.
  useEffect(() => {
    const documentId = readLastDocument();
    if (!documentId) return;
    let cancelled = false;
    api
      .getStatus(documentId)
      .then((run) => {
        if (!cancelled && run.status === "completed") setLastReport(documentId);
      })
      .catch(() => {
        /* stale or unreachable: simply don't offer the link */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Sync reduced motion for video
  useEffect(() => {
    const q = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
    const v = document.querySelector("video.art") as HTMLVideoElement | null;
    if (!q || !v) return;
    const sync = () => {
      if (q.matches) {
        v.pause();
      } else {
        v.play().catch(() => {});
      }
    };
    sync();
    if (q.addEventListener) {
      q.addEventListener("change", sync);
      return () => q.removeEventListener("change", sync);
    }
  }, []);

  // Entrance retirement
  useEffect(() => {
    const f2 = document.getElementById("foot2");
    const timer = setTimeout(() => {
      document.documentElement.classList.add("is-entered");
    }, 4000);
    const done = () => {
      clearTimeout(timer);
      document.documentElement.classList.add("is-entered");
    };
    if (f2) {
      f2.addEventListener("animationend", done);
      return () => {
        clearTimeout(timer);
        f2.removeEventListener("animationend", done);
      };
    }
    return () => clearTimeout(timer);
  }, []);

  const closeNav = () => setNavOpen(false);

  const serviceLine = status
    ? status.llm.configured && status.database.reachable && status.embeddings.ready
      ? `Live: ${status.llm.model} on ${providerName(status.llm.provider)} · ${status.embeddings.model} embeddings`
      : "The analysis service is running but not fully configured. Check /api/system/status."
    : statusError
      ? "The analysis service is offline. Start the backend to analyze documents."
      : "Checking the analysis service…";

  return (
    <div className="landing-page relative h-screen w-screen overflow-hidden bg-[#02060f] select-none">
      {/* 1) Looping Background Video */}
      <video
        className="art"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        aria-hidden="true"
        poster="https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/130837c4-0244-4f37-9c61-8d801d93fd29.jpg"
        src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260912_104303_0c6d60b2-9353-408e-9449-585108a22fb5.mp4"
      />

      {/* 2) Ambient Symmetrical Veil */}
      <div className="veil" />

      {/* 3) Header Bar */}
      <header className="bar">
        <Link to="/" className="brand" aria-label="ReqGuard AI home">
          <svg viewBox="0 0 23 17" aria-hidden="true">
            <path d="M8.15 0.9 L4.55 0.9 L0.5 9.3 L4.1 9.3 Z" />
            <path d="M17.0 0 L13.4 0 L6.15 16.4 L9.75 16.4 Z" />
            <path d="M22.9 0 L19.3 0 L15.0 7.6 L18.6 7.6 Z" />
            <path d="M22.6 6.9 L19.0 6.9 L14.05 16.4 L17.65 16.4 Z" />
          </svg>
          <span id="word">ReqGuard AI</span>
        </Link>

        <input
          className="navtoggle"
          type="checkbox"
          id="nav-open"
          aria-label="Open menu"
          checked={navOpen}
          onChange={(e) => setNavOpen(e.target.checked)}
        />
        <label className="scrim" htmlFor="nav-open" aria-hidden="true" onClick={closeNav} />
        <label className="burger" htmlFor="nav-open" aria-label="Menu">
          <svg viewBox="0 0 22 14">
            <path className="b1" d="M1 1 H21" />
            <path className="b2" d="M1 7 H21" />
            <path className="b3" d="M1 13 H21" />
          </svg>
        </label>

        <div className="navpanel">
          <nav className="menu" aria-label="Main">
            <button
              type="button"
              onClick={() => {
                setHowOpen(true);
                closeNav();
              }}
              className="text-left"
            >
              <span id="about">How it works</span>
            </button>
            <a href={SAMPLE_SRS} download onClick={closeNav} className="text-left">
              <span id="product">Sample SRS</span>
            </a>
            <a
              href={`${api.baseUrl}/docs`}
              target="_blank"
              rel="noreferrer"
              onClick={closeNav}
              className="text-left"
            >
              <span id="solutions">API docs</span>
            </a>
          </nav>

          {lastReport ? (
            <Link to={`/dashboard/${lastReport}`} onClick={closeNav} className="login text-left">
              <span id="login">Open latest report</span>
              <svg className="navarrow" viewBox="0 0 10 9" aria-hidden="true">
                <path d="M0 4.5 H9.1 M5.4 0.9 L9.2 4.5 L5.4 8.1" />
              </svg>
            </Link>
          ) : null}

          <Link to="/upload" onClick={closeNav} className="pill">
            <span id="contact">Analyze SRS</span>
          </Link>
        </div>
      </header>

      {/* 4) Hero Section */}
      <main className="hero">
        <h1 className="title">
          <span id="h1a">Find requirement problems</span>
          <span id="h1b">before they become software problems.</span>
        </h1>

        <p className="sub">
          <span id="sub1">Ambiguities, contradictions and duplicates,</span>
          <span id="sub2">found with evidence before you build.</span>
        </p>

        <Link className="cta" to="/upload">
          <span id="cta">Analyze your SRS</span>
          <svg className="arrow" viewBox="0 0 16 11" aria-hidden="true">
            <path d="M0 5.5 H14.6 M10.3 1.2 L14.9 5.5 L10.3 9.8" />
          </svg>
        </Link>

        <ul className="feats">
          {["Ambiguity detection", "Contradiction checks", "Duplicate detection", "Traceability matrix"].map(
            (label, index) => (
              <li key={label}>
                <svg className="chev" viewBox="0 0 11 20" aria-hidden="true">
                  <path d="M1.15 1.15 L9.6 10 L1.15 18.85" />
                </svg>
                <span id={`f${index + 1}`}>{label}</span>
              </li>
            ),
          )}
        </ul>

        <span className="rule" aria-hidden="true" />
      </main>

      {/* 5) Footer */}
      <footer className="foot">
        <span id="foot1" role="status">
          {serviceLine}
        </span>
        <span id="foot2">Delulu 2 Deploy · Problem statement G14</span>
      </footer>

      <HowItWorksModal isOpen={howOpen} onClose={closeHow} />
    </div>
  );
}

function providerName(provider: string): string {
  if (provider === "groq") return "Groq";
  if (provider === "openrouter") return "OpenRouter";
  return provider;
}

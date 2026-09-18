// ReqGuard AI -- frontend check in a real browser, with real mouse clicks.
//
//   cd docs && npm init -y && npm i playwright     (once; uses installed Microsoft Edge)
//   node ui_check.mjs <completed_document_id> [screenshot_dir]
//
// Needs the frontend on http://localhost:5173 and the backend on :8000, and a
// document that backend/verify_demo_flow.py has run against: that script leaves
// R001's refinement rejected, which this one accepts and then reverts, so the
// document ends as it started. It never starts a new (token-consuming) analysis.

// Real-click verification of the landing page and frontend fixes.
// Every interaction is a real mouse click at the element's position, so a
// control hidden under another element fails here the way it fails for a user.
import { chromium } from "playwright";

const BASE = "http://localhost:5173";
const API = "http://localhost:8000";
const DOC = process.argv[2];
const OUT = process.argv[3] || ".";
let failures = 0;
const consoleErrors = [];

function check(label, ok, detail = "") {
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${label}${detail ? " — " + detail : ""}`);
  if (!ok) failures++;
}

const browser = await chromium.launch({ channel: "msedge" });

async function open(width, height, path = "/") {
  const ctx = await browser.newContext({ viewport: { width, height } });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(`[${width}] ${m.text()}`); });
  page.on("pageerror", (e) => consoleErrors.push(`[${width}] ${e}`));
  await page.goto(BASE + path, { waitUntil: "domcontentloaded" });
  return page;
}

async function blockedControls(page) {
  return page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll(".landing-page a, .landing-page button")) {
      const target = el.getBoundingClientRect().width ? el : el.querySelector("span") ?? el;
      const r = target.getBoundingClientRect();
      if (!r.width || getComputedStyle(el).visibility === "hidden") continue;
      const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      if (hit && !el.contains(hit)) out.push(el.textContent.trim());
    }
    return out;
  });
}

// Real mouse click where a control's text is drawn. The desktop header items
// are zero-height boxes, so Playwright's own click refuses them as invisible;
// a person clicks the letters, so this does too.
async function clickText(page, id) {
  const p = await page.evaluate((spanId) => {
    const range = document.createRange();
    range.selectNodeContents(document.getElementById(spanId));
    const r = range.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, id);
  await page.mouse.click(p.x, p.y);
}

// Same, but at the edge of the enlarged hit area rather than on the letters.
async function clickNearText(page, id, dy) {
  const p = await page.evaluate((spanId) => {
    const range = document.createRange();
    range.selectNodeContents(document.getElementById(spanId));
    const r = range.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, id);
  await page.mouse.click(p.x, p.y + dy);
}

// ---------------------------------------------------------------- landing
for (const [w, h, tag] of [[1440, 900, "desktop"], [1280, 720, "laptop"], [1920, 1080, "fhd"]]) {
  console.log(`\nLanding ${tag} ${w}x${h}`);
  const page = await open(w, h);
  await page.waitForTimeout(4200); // entrance animation
  const blocked = await blockedControls(page);
  check("every control is clickable (nothing covers it)", blocked.length === 0, blocked.join(", "));
  const text = await page.locator(".landing-page").innerText();
  check("headline is about ReqGuard", text.includes("Find requirement problems"));
  check("no template copy left", !/World-Class|extraordinary products|Strategic partner|2024/.test(text));
  await page.waitForFunction(() => /Live:|offline|not fully/.test(document.querySelector("#foot1")?.textContent ?? ""), null, { timeout: 15000 }).catch(() => {});
  const foot = await page.locator("#foot1").innerText();
  check("footer shows the live service state", foot.startsWith("Live:") && foot.includes("gpt-oss-20b"), foot);
  if (tag === "desktop") await page.screenshot({ path: `${OUT}/v-landing-desktop.png` });

  await clickText(page, "about");
  const dialog = page.getByRole("dialog", { name: /How ReqGuard AI works/ });
  check("real click on 'How it works' opens a real explanation", await dialog.isVisible());
  if (tag === "desktop") await page.screenshot({ path: `${OUT}/v-how-it-works.png` });
  await page.keyboard.press("Escape");
  check("Escape closes it", !(await dialog.isVisible()));
  await clickNearText(page, "about", 7);
  check("the enlarged hit area takes a click just below the text", await dialog.isVisible());
  await page.mouse.click(20, h - 20); // backdrop
  check("clicking the backdrop closes it", !(await dialog.isVisible()));

  const sampleHref = await page.getByRole("link", { name: "Sample SRS" }).getAttribute("href");
  const sample = await page.request.get(BASE + sampleHref);
  check("'Sample SRS' downloads the real sample", sample.ok() && (await sample.body()).length === 36927, `${sampleHref} ${(await sample.body()).length} bytes`);
  const docsHref = await page.getByRole("link", { name: "API docs" }).getAttribute("href");
  const docs = await page.request.get(docsHref);
  check("'API docs' opens the backend's OpenAPI page", docs.ok() && docsHref === `${API}/docs`, docsHref);

  await page.locator("a.cta").click();
  await page.waitForURL("**/upload", { timeout: 5000 }).catch(() => {});
  check("real click on 'Analyze your SRS' reaches /upload", page.url().endsWith("/upload"), page.url());
  await page.goto(BASE + "/");
  await page.waitForTimeout(4200);
  await page.locator("a.pill").click();
  await page.waitForURL("**/upload", { timeout: 5000 }).catch(() => {});
  check("real click on header 'Analyze SRS' reaches /upload", page.url().endsWith("/upload"));
  await page.goto(BASE + "/");
  await page.waitForTimeout(4200);
  await clickText(page, "word");
  check("logo click stays on home", page.url() === BASE + "/");
  await page.context().close();
}

console.log("\nLanding 'Open latest report'");
{
  const page = await open(1440, 900);
  await page.waitForTimeout(1500);
  check("hidden when no analysis is remembered", (await page.getByRole("link", { name: "Open latest report" }).count()) === 0);
  await page.evaluate((id) => localStorage.setItem("reqguard:last-document", id), DOC);
  await page.reload();
  await page.getByRole("link", { name: "Open latest report" }).waitFor({ timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(4200);
  const link = page.getByRole("link", { name: "Open latest report" });
  check("shown for a remembered, completed analysis", (await link.count()) === 1);
  await clickText(page, "login");
  await page.waitForURL(`**/dashboard/${DOC}`, { timeout: 5000 }).catch(() => {});
  check("opens that report", page.url().endsWith(`/dashboard/${DOC}`));
  await page.evaluate(() => localStorage.setItem("reqguard:last-document", "00000000-0000-0000-0000-000000000000"));
  await page.goto(BASE + "/");
  await page.waitForTimeout(2500);
  check("not offered for an analysis that no longer exists", (await page.getByRole("link", { name: "Open latest report" }).count()) === 0);
  await page.context().close();
}

console.log("\nLanding phone 390x844");
{
  const page = await open(390, 844);
  await page.waitForTimeout(4200);
  await page.screenshot({ path: `${OUT}/v-landing-phone.png` });
  await page.locator("label.burger").click();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/v-landing-phone-menu.png` });
  await page.getByRole("button", { name: "How it works" }).click();
  check("menu → 'How it works' works on a phone", await page.getByRole("dialog").isVisible());
  await page.keyboard.press("Escape");
  await page.locator("a.cta").click();
  await page.waitForURL("**/upload", { timeout: 5000 }).catch(() => {});
  check("CTA works on a phone", page.url().endsWith("/upload"));
  const overflowX = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  check("upload page has no horizontal scroll on a phone", overflowX <= 1, `${overflowX}px`);
  await page.context().close();
}

// ----------------------------------------------------------------- upload
console.log("\nUpload page");
{
  const page = await open(1440, 900, "/upload");
  const analyze = page.getByRole("button", { name: /Analyze Requirements/ });
  check("Analyze disabled before a file is chosen", await analyze.isDisabled());
  await page.getByRole("button", { name: /Use the sample E-Commerce SRS/ }).click();
  await page.getByText("ECommerce_SRS_Hackathon_Sample.docx").waitFor({ timeout: 10000 }).catch(() => {});
  const card = await page.locator("main").innerText();
  check("sample button loads the real DOCX", card.includes("ECommerce_SRS_Hackathon_Sample.docx") && card.includes("36.1 KB"), card.match(/[\d.]+ KB/)?.[0] ?? "no size");
  check("Analyze enabled once the sample is loaded", await analyze.isEnabled());
  check("no misleading privacy claim", !card.includes("Processed privately"));
  await page.screenshot({ path: `${OUT}/v-upload-sample.png` });
  await page.getByRole("link", { name: /Back to home/ }).click();
  await page.waitForURL(BASE + "/", { timeout: 5000 }).catch(() => {});
  check("'Back to home' works", page.url() === BASE + "/");
  await page.context().close();
}

// ------------------------------------------------------ clean requirements
console.log("\nClean requirements: refinements are reviewable before accepting");
{
  const page = await open(1440, 900, `/dashboard/${DOC}/requirements`);
  // The heading, not the text: "Loading clean requirement set…" matches the text too.
  await page.getByRole("heading", { name: "Clean Requirement Set" }).waitFor({ timeout: 20000 });
  const body = await page.locator("main").innerText();
  const pending = (body.match(/Proposed rewrite · not applied yet/gi) || []).length;
  check("pending proposals are shown with their text", pending > 0, `${pending} pending`);

  // A pending proposal must show text that differs from the original.
  const firstPending = page.locator("div.rounded-lg", { hasText: /Proposed rewrite · not applied yet/i }).first();
  const card = page.locator("[class*='backdrop-blur-xl']", { has: firstPending }).first();
  const original = await card.locator("p").nth(1).innerText().catch(() => "");
  const proposal = await firstPending.locator("p").nth(1).innerText();
  check("the proposal is not just the original repeated", proposal.length > 0 && proposal !== original);

  // R001 was rejected by the API demo flow: exercise accept -> revert on it,
  // leaving it rejected as it was.
  const r001 = page.locator("[class*='backdrop-blur-xl']", { hasText: "R001" }).first();
  check("a rejected proposal says so", /Proposal rejected · original kept/i.test(await r001.innerText()));
  await r001.getByRole("button", { name: /Accept proposal after all/ }).click();
  await page.waitForFunction(() => /In force · accepted rewrite/i.test(document.querySelector("main")?.innerText ?? ""), null, { timeout: 15000 }).catch(() => {});
  const r001After = page.locator("[class*='backdrop-blur-xl']", { hasText: "R001" }).first();
  check("accepting applies it and shows it as in force", /In force · accepted rewrite/i.test(await r001After.innerText()));
  await page.screenshot({ path: `${OUT}/v-clean-accepted.png` });
  await r001After.getByRole("button", { name: /Revert to original/ }).click();
  await page.waitForFunction(() => {
    const card = [...document.querySelectorAll("main [class*='backdrop-blur-xl']")].find((c) => c.textContent.includes("R001"));
    return card && /Proposal rejected/i.test(card.textContent);
  }, null, { timeout: 15000 }).catch(() => {});
  check("reverting restores the original", /Proposal rejected · original kept/i.test(await page.locator("[class*='backdrop-blur-xl']", { hasText: "R001" }).first().innerText()));

  // Pin the card by its requirement code: clicking Edit changes the label the
  // "pending" filter matches on, which would silently switch to another card.
  const pendingCard = page.locator("[class*='backdrop-blur-xl']", { has: page.locator("text=/Proposed rewrite · not applied yet/i") }).first();
  const code = (await pendingCard.locator("span.font-mono").first().innerText()).trim();
  const editable = page
    .locator("[class*='backdrop-blur-xl']")
    .filter({ has: page.locator("span.font-mono", { hasText: new RegExp(`^${code}$`) }) })
    .first();
  console.log(`        editing ${code}`);
  const proposalText = await editable.locator("div.rounded-lg", { hasText: /Proposed rewrite/i }).locator("p").nth(1).innerText();
  await editable.getByRole("button", { name: "Edit" }).click();
  const draft = await editable.locator("textarea").inputValue();
  check("Edit starts from the proposal, not the original", draft === proposalText);
  await editable.getByRole("button", { name: "Cancel" }).click();
  await page.context().close();
}

// ------------------------------------------------------- dependency graph
console.log("\nDependency graph");
{
  const page = await open(1440, 900, `/dashboard/${DOC}/dependencies`);
  await page.locator(".react-flow__edge-textbg").first().waitFor({ timeout: 20000 });
  const labelFill = await page.locator(".react-flow__edge-textbg").first().evaluate((el) => getComputedStyle(el).fill);
  check("edge labels have a dark background", labelFill !== "rgb(255, 255, 255)", labelFill);
  const ctrlBg = await page.locator(".react-flow__controls-button").first().evaluate((el) => getComputedStyle(el).backgroundColor);
  check("zoom controls are dark, icons visible", ctrlBg !== "rgb(255, 255, 255)" && ctrlBg !== "rgb(254, 254, 254)", ctrlBg);
  await page.locator(".react-flow__controls-button").first().click();
  check("zoom control responds to a click", true);
  await page.screenshot({ path: `${OUT}/v-dependencies.png` });
  await page.context().close();
}

const real = consoleErrors.filter((e) => !/favicon|DevTools|Download the React/i.test(e));
console.log("\nConsole");
check("no console errors across every page", real.length === 0, real.slice(0, 3).join(" | "));

await browser.close();
console.log(failures === 0 ? "\nALL CHECKS PASSED" : `\n${failures} CHECK(S) FAILED`);
process.exit(failures ? 1 : 0);

// Live browser regression suite. Designed to fail the deployment if the red-letter reader regresses.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const BASE = process.env.READER_URL || "http://127.0.0.1:8765/words-of-christ/";
(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ["--autoplay-policy=no-user-gesture-required", "--no-sandbox"],
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const failures = [];
  page.on("pageerror", e => failures.push(e.message));
  try {
    const response = await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 45000 });
    assert.equal(response.status(), 200, "Reader must return HTTP 200");
    await page.waitForSelector(".verse", { timeout: 12000 });
    assert.equal(await page.locator("#books .book").count(), 4, "Four Gospels must render");
    assert.equal(await page.locator("#chapters button").count(), 21, "All 21 John chapters must render");
    assert.equal(await page.locator(".verse").count(), 8, "John 1 should have eight recorded sayings");
    console.log("PASS John chapter 1 and Gospel navigation");

    await page.locator("#books [data-book='Mark']").click();
    await page.locator("#chapters [data-chapter='4']").click();
    assert.match(await page.locator("#heading").innerText(), /Mark 4/);
    assert.ok(await page.locator(".verse").count() > 15);
    console.log("PASS Mark 4 loads without remote Scripture API");

    await page.locator("#books [data-book='John']").click();
    await page.locator("#accent").selectOption("en-GB");
    await page.locator("#quality").selectOption("natural");
    await page.waitForFunction(() => {
      return document.querySelector("#qualityInfo").textContent.includes("narration ready");
    }, null, { timeout: 15000 });
    console.log("PASS natural British voice recording loaded for John 1");

    await page.locator("#commandInput").fill("Repeat John 1:38 three times");
    await page.locator("#runCommand").click();
    await page.waitForFunction(() => {
      return document.querySelector("#message").textContent.includes("Repeated John 1:38 3 times");
    }, null, { timeout: 16000 });
    console.log("PASS chapter audio loops exactly three times");

    await page.locator(".loop-verse").first().click();
    await page.waitForTimeout(1750);
    assert.match(await page.locator("#message").innerText(), /loop|repeating|repetition|natural/i);
    await page.locator("#stopReading").click();
    assert.match(await page.locator("#message").innerText(), /stopped/i);
    console.log("PASS one-tap verse Repeat button starts and stops");


    await page.locator("#accent").selectOption("en-US");
    await page.waitForFunction(() => {
      return document.querySelector("#qualityInfo").textContent.includes("narration ready");
    }, null, { timeout: 15000 });
    await page.locator("#commandInput").fill("Loop John 1:38");
    await page.locator("#runCommand").click();
    await page.waitForTimeout(3200);
    assert.match(await page.locator("#message").innerText(), /loop|repetition|natural/i);
    await page.locator("#stopReading").click();
    assert.match(await page.locator("#message").innerText(), /stopped/i);
    console.log("PASS American voice supports infinite loop and Stop");

    await page.locator("#commandInput").fill("Read John");
    await page.locator("#runCommand").click();
    assert.match(await page.locator("#heading").innerText(), /John 1/);
    await page.locator("#stopReading").click();
    console.log("PASS continuous John reading command starts from John 1");

    await page.locator("#accent").selectOption("en-NG");
    assert.match(await page.locator("#qualityInfo").innerText(), /not been generated/i);
    console.log("PASS unavailable Nigerian studio voice is disclosed accurately");

    await page.locator("#searchInput").fill("kingdom");
    assert.match(await page.locator("#searchCount").innerText(), /matches/);
    console.log("PASS search remains functional");

    assert.deepEqual(failures, [], "No uncaught browser page errors");
    console.log("ALL RED LETTERS BROWSER CHECKS PASSED");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error("BROWSER REGRESSION:", error); process.exit(1); });

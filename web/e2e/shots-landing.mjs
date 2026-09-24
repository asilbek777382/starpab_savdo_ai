// Landing skrinshotlari: node e2e/shots-landing.mjs <base_url> <out_dir>
import { chromium } from "playwright";

const [base = "http://localhost:4173", out = "."] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["mobile", { width: 390, height: 844 }]]) {
  for (const lang of ["uz", "ru"]) {
    const page = await browser.newPage({ viewport });
    await page.addInitScript((l) => localStorage.setItem("nv_lang", l), lang);
    await page.goto(base + "/");
    await page.waitForTimeout(6500); // demo suhbat to'lsin
    await page.screenshot({ path: `${out}/landing-${name}-${lang}.png`, fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    console.log(name, lang, "horizontal overflow:", overflow);
    await page.close();
  }
}
await browser.close();

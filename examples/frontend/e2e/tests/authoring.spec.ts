import { expect, test } from "@playwright/test";

// The authoring agent, end-to-end through the browser against `serve --demo-data` (which wires a
// deterministic, offline ScriptedLLM): open the panel, describe a bot, and the agent proposes a
// validated bot for review.
test("author a bot via the agent — propose and review", async ({ page }) => {
  await page.goto("/");
  // the agent dock is always present on the right — no toggle to open
  await page.getByTestId("author-input").fill("flag high-value orders");
  await page.getByTestId("author-propose").click();

  const proposed = page.getByTestId("proposed-bot");
  await expect(proposed).toContainText("high-value-orders", { timeout: 15_000 });
  await expect(proposed).toContainText("valid");
});

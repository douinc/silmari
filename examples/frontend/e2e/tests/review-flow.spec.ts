import { expect, test } from "@playwright/test";

// The full loop, end to end through the browser + API + engine:
//   select a bot -> trigger a run -> SSE delivers run_completed -> accept a case -> tuning updates.
test("select bot, run, receive SSE completion, review a case, see tuning", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("health")).toContainText("ok");

  await page.getByTestId("bot-example-signal").click();
  await expect(page.getByTestId("selected-bot")).toHaveText("example-signal");

  // Trigger a run; the live SSE log must show the lifecycle event end-to-end over HTTP.
  await page.getByTestId("run-now").click();
  await expect(page.getByTestId("event-log")).toContainText("run_completed", { timeout: 20_000 });

  // The run flagged one case (order total >= 75) — accept it.
  const accept = page.getByTestId("accept-0");
  await expect(accept).toBeVisible();
  await accept.click();
  await expect(page.getByTestId("decision-0")).toHaveText("accepted");
  await expect(page.getByTestId("tally")).toContainText("accepted 1");

  // Tuning reflects the labeled case.
  await page.getByTestId("tab-tuning").click();
  await expect(page.getByTestId("tuning")).toContainText("labeled 1");

  // AGPL §13: the running service offers its source to every user.
  await expect(page.getByTestId("source-link")).toBeVisible();
});
